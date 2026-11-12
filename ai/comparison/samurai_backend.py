"""Official SAMURAI temporal model; independent, mask-constrained physical-point LK.

The bounded frame loader changes storage only. Kalman state and SAMURAI memory
selection remain in the pinned upstream predictor, never reset between batches.
"""
import argparse
import contextlib
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
REVISION = '76ba195984892b0d1e3db5d9c9f90bb62175680a'
CHECKPOINT_SHA256 = '6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38'
CONFIG = 'configs/samurai/sam2.1_hiera_s.yaml'
VERSION = 'samurai-official-physical-point-1'


def validate_target(target, frames, width, height):
    index = target['frameIndex']
    if not isinstance(index, int) or not 0 <= index < len(frames):
        raise ValueError('Target frameIndex is outside the video')
    if abs(target['timestampSeconds']-frames[index]['timestampSeconds']) > .001:
        raise ValueError('Target timestamp does not match its frameIndex')
    box, point = target['box'], target['point']
    values = [box[k] for k in ('x','y','width','height')] + [point[k] for k in ('x','y')]
    if not all(isinstance(v, (int,float)) and math.isfinite(v) for v in values):
        raise ValueError('Target coordinates must be finite')
    x,y,w,h = values[:4]
    if not (w>0 and h>0 and 0<=x<x+w<=width and 0<=y<y+h<=height):
        raise ValueError('Target box is outside the video')
    if not (x <= point['x'] < x+w and y <= point['y'] < y+h):
        raise ValueError('Physical measurement point must lie inside the target box')
    if not target.get('targetId') or not isinstance(target.get('athleteTrackId'), int):
        raise ValueError('Target must identify an athlete and physical object')


def scalar(value):
    return float(value.item()) if hasattr(value, 'item') else float(value)


def memory_keep_indices(outputs, current, pointer_count, iou_threshold, object_threshold, kf_threshold):
    """Preserve exactly every heavy memory a subsequent forward step can request.

    Upstream scans all score history for its last pointer_count-1 accepted frames;
    retain that score history even after freeing ineligible feature tensors.
    """
    eligible = [i for i, o in outputs.items() if i > 1
                and scalar(o['best_iou_score']) > iou_threshold
                and scalar(o['object_score_logits']) > object_threshold
                and (o.get('kf_score') is None or scalar(o['kf_score']) > kf_threshold)]
    return set(sorted(eligible)[-(pointer_count-1):]) | set(range(max(0,current-pointer_count+1),current+1))


def trim_memory(state, predictor, current):
    outputs = state['output_dict']['non_cond_frame_outputs']
    keep = memory_keep_indices(outputs,current,predictor.max_obj_ptrs_in_encoder,
        predictor.memory_bank_iou_threshold,predictor.memory_bank_obj_score_threshold,
        predictor.memory_bank_kf_score_threshold)
    for index, output in outputs.items():
        if index not in keep:
            for key in ('maskmem_features','maskmem_pos_enc','pred_masks','obj_ptr'):
                output.pop(key,None)
            for key in ('best_iou_score','object_score_logits','kf_score'):
                if output.get(key) is not None:
                    output[key] = output[key].cpu() if hasattr(output[key],'cpu') else output[key]
            for rows in state['output_dict_per_obj'].values():
                rows['non_cond_frame_outputs'].pop(index,None)


class LazyFrames:
    """One decoded BGR image and one normalized tensor, with exact PTS validation."""
    def __init__(self, path, frames, start, image_size):
        from motiontrace_ai.video_decode import VideoDecoder
        self.decoder = VideoDecoder(path)
        self.iterator = iter(self.decoder)
        self.frames, self.start, self.image_size = frames, start, image_size
        self.index, self.image, self.tensor = -1, None, None
        self.height,self.width = self.decoder.height,self.decoder.width

    def __len__(self): return len(self.frames)-self.start

    def __getitem__(self, index):
        import cv2
        import numpy as np
        import torch
        from PIL import Image
        absolute = index+self.start
        if absolute < self.index or not 0<=index<len(self):
            raise IndexError('SAMURAI loader supports monotonic forward tracking only')
        while self.index < absolute:
            row = next(self.iterator, None)
            if row is None: raise ValueError('Video ended before the shared pose timeline')
            self.index += 1
            timestamp,self.image = row
            if abs(timestamp-self.frames[self.index]['timestampSeconds']) > .001:
                raise ValueError('Video timestamp differs from shared pose frame')
            self.tensor = None
        if self.tensor is None:
            rgb = Image.fromarray(cv2.cvtColor(self.image,cv2.COLOR_BGR2RGB))
            # Same Pillow resize and ImageNet normalization as official JPEG loader.
            resized = np.asarray(rgb.resize((self.image_size,self.image_size))).copy()
            self.tensor = torch.from_numpy(resized).permute(2,0,1).float()/255.
            self.tensor.sub_(torch.tensor([.485,.456,.406])[:,None,None])
            self.tensor.div_(torch.tensor([.229,.224,.225])[:,None,None])
        return self.tensor

    def finish(self):
        if self.index != len(self.frames)-1 or next(self.iterator,None) is not None:
            raise ValueError('Video frame count differs from shared pose timeline')


def run(args):
    import cv2
    import numpy as np
    import torch
    from motiontrace_ai.video_decode import validate_analysis_frames
    from vision.measurement import MeasurementPoint
    from vision.analyze import atomic_json
    root = Path(args.models_root).resolve()
    manifest_path = root/'manifest.json'
    if not manifest_path.is_file():
        raise FileNotFoundError('SAMURAI is not installed. Run scripts/setup-samurai.ps1')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    checkpoint = root/'sam2.1_hiera_small.pt'
    with checkpoint.open('rb') as stream:
        checkpoint_hash=hashlib.file_digest(stream,'sha256').hexdigest()
    if manifest.get('revision') != REVISION or checkpoint_hash!=CHECKPOINT_SHA256:
        raise ValueError('SAMURAI revision/checkpoint integrity mismatch; reinstall explicitly')
    for record in manifest['files']:
        with (root/record['path']).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=record['sha256']:
                raise ValueError('SAMURAI installed source integrity mismatch: '+record['path'])
    import sam2
    from sam2.build_sam import build_sam2_video_predictor
    import sam2.sam2_video_predictor as module
    expected_source = root/'source'/'sam2'/'sam2'
    if Path(sam2.__file__).resolve().parent != expected_source:
        raise RuntimeError('Wrong sam2 package: SAMURAI requires its own interpreter')
    pose = json.loads(Path(args.pose_input).read_text(encoding='utf-8-sig'))
    validate_analysis_frames(pose)
    target = json.loads(Path(args.target).read_text(encoding='utf-8-sig'))
    frames = pose['frames']
    torch.set_num_threads(4)
    started = time.perf_counter()
    device = torch.device(args.device)
    if device.type=='cuda': torch.cuda.reset_peak_memory_stats(device)
    loader = LazyFrames(args.input,frames,target['frameIndex'],1024)
    validate_target(target,frames,loader.width,loader.height)
    if (pose['video']['width'],pose['video']['height']) != (loader.width,loader.height):
        loader.decoder.close()
        raise ValueError('Shared pose dimensions differ from the rotated video')
    if target['athleteTrackId'] not in {a['id'] for a in pose['athletes']}:
        loader.decoder.close()
        raise ValueError('Target athlete does not exist in shared pose analysis')
    mask_root = Path(args.output).resolve().with_suffix('.masks')
    mask_root.mkdir(parents=True,exist_ok=True)
    original_loader = module.load_video_frames
    module.load_video_frames = lambda **kwargs: (loader,loader.height,loader.width)
    raw = []
    output_frames = [dict(f,shaft=None,shafts=[],objects=[]) for f in frames]
    try:
        with torch.inference_mode(), torch.autocast(device.type,dtype=torch.bfloat16,enabled=device.type=='cuda'):
            predictor = build_sam2_video_predictor(CONFIG,str(checkpoint),device=args.device,
                apply_postprocessing=False)
            if not predictor.samurai_mode: raise RuntimeError('SAMURAI motion-aware mode is disabled')
            state = predictor.init_state(str(args.input),offload_video_to_cpu=True,offload_state_to_cpu=True)
            b = target['box']
            predictor.add_new_points_or_box(state,frame_idx=0,obj_id=1,
                box=np.array([b['x'],b['y'],b['x']+b['width'],b['y']+b['height']],np.float32))
            point = MeasurementPoint()
            for local_index, ids, logits in predictor.propagate_in_video(state,start_frame_idx=0):
                index = local_index+target['frameIndex']
                mask = (logits[0,0]>0).cpu().numpy()
                seed = [target['point']['x'],target['point']['y']] if local_index==0 else None
                measurement = point.update(loader.image,mask,correction=seed)
                output = state['output_dict']['cond_frame_outputs' if local_index==0 else 'non_cond_frame_outputs'][local_index]
                score = scalar(output['object_score_logits'])
                # Upstream consolidation omits affinity on the conditioning frame.
                affinity = scalar(output['best_iou_score']) if 'best_iou_score' in output else None
                ys,xs = np.nonzero(mask)
                box = dict(x=int(xs.min()),y=int(ys.min()),width=int(xs.max()-xs.min()+1),height=int(ys.max()-ys.min()+1)) if xs.size else None
                mask_path = mask_root/f'{index:08d}.png'
                if not cv2.imwrite(str(mask_path),mask.astype(np.uint8)*255): raise IOError('Failed to save SAMURAI mask')
                visible = bool(xs.size) and score>0
                if not visible: measurement=None
                obj = dict(objectId=str(target['targetId']),athleteId=target['athleteTrackId'],box=box,
                    maskPath=str(mask_path),trackingState='Tracked' if visible else 'Lost',
                    confidence=float(torch.sigmoid(torch.tensor(score))),measurement=measurement)
                output_frames[index]['objects']=[obj]
                raw.append(dict(frameIndex=index,timestampSeconds=frames[index]['timestampSeconds'],
                    maskPath=str(mask_path),maskBox=box,objectScoreLogit=score,maskAffinity=affinity,
                    kalmanScore=scalar(output['kf_score']) if output.get('kf_score') is not None else None,
                    visible=visible,measurement=measurement))
                trim_memory(state,predictor,local_index)
                if index%30==0:
                    fraction=(index+1)/len(frames)
                    print(json.dumps(dict(type='progress',value=fraction,progress=fraction,message='SAMURAI motion-aware tracking')),file=sys.__stdout__,flush=True)
            loader.finish()
    finally:
        module.load_video_frames=original_loader
        loader.decoder.close()
    raw_path=Path(args.output).with_suffix('.raw.json')
    atomic_json(raw_path,dict(schemaVersion=1,provider='samurai',observations=raw))
    result=dict(pose,schemaVersion=4,frames=output_frames,provider='samurai')
    result['rawObservationsPath']=str(raw_path.resolve())
    result['versions']=dict(pose['versions'],barbellProvider='samurai',barbellModelVersion=REVISION,
                            measurementVersion=VERSION)
    result['backend']=dict(provider='samurai',version=VERSION,revision=REVISION,
        checkpoint=checkpoint.name,checkpointSha256=CHECKPOINT_SHA256,configuration=CONFIG,
        samuraiMode=True,resolution=1024,mode='forward-temporal',precision='bfloat16' if device.type=='cuda' else 'float32',
        measurementMethod='manual-lk constrained by independent SAMURAI mask',isProxy=False,
        scoreMeaning='sigmoid object-presence logit; not calibrated against other providers',
        holeFilling=False,rawObservationsPath=str(raw_path.resolve()),target=target,
        elapsedSeconds=time.perf_counter()-started,
        peakVramBytes=torch.cuda.max_memory_allocated(device) if device.type=='cuda' else None)
    result['visionMetadata']=result['backend']
    atomic_json(args.output,result)
    print(json.dumps(dict(type='progress',value=1.,progress=1.,message='SAMURAI tracking complete')),file=sys.__stdout__,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for option in ('input','pose-input','target','output','models-root'): parser.add_argument('--'+option,required=True)
    parser.add_argument('--device',default='cuda:0')
    with contextlib.redirect_stdout(sys.stderr): run(parser.parse_args())
