"""Existing DINO/SAM tracker, independently prompted with the shared physical point."""
import argparse
import contextlib
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision.analyze import atomic_json


def run(args):
    import torch
    from vision.pipeline import track_objects, verify_manifest
    torch.set_num_threads(4)
    started=time.perf_counter()
    pose=json.loads(Path(args.pose_input).read_text(encoding='utf-8-sig'))
    target=json.loads(Path(args.target).read_text(encoding='utf-8-sig'))
    root=Path(args.models_root)
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8-sig'))
    verify_manifest(root,manifest,names=('grounding_dino','sam2'))
    protocol=sys.stdout
    def report(fraction,message):
        print(json.dumps(dict(stage=message,fraction=fraction)),file=protocol,flush=True)
    box=target['box']; point=target['point']; owner=target['athleteTrackId']
    corrections={target['frameIndex']:[dict(objectId=target['targetId'],athleteId=owner,
        point=[point['x'],point['y']],box=[box['x'],box['y'],box['x']+box['width'],box['y']+box['height']])]}
    with contextlib.redirect_stdout(sys.stderr):
        # Shared preparation already proposed/validated this manual target box.
        # track_objects ignores detector assignments for a manually prompted owner.
        objects=track_objects(args.input,pose['frames'],{},corrections,Path(args.output).parent/'masks',root,args.device,report)
    if len(objects)!=len(pose['frames']):raise ValueError('Incomplete DINO/SAM tracking timeline')
    result=dict(pose,schemaVersion=4,provider='grounding_dino_sam2')
    result['frames']=[dict(f,shaft=None,shafts=[],objects=items) for f,items in zip(pose['frames'],objects)]
    result['athletes']=[dict(a,isExerciseParticipant=a['id']==owner) for a in pose['athletes']]
    result['versions']=dict(pose['versions'],barbellProvider='grounding_dino_sam2',measurementVersion='manual-lk-in-sam-mask-1')
    result['visionMetadata']=dict(provider='grounding_dino_sam2',target=target,models=manifest,
        measurementMethod='physical-point-lk-mask-validation',isProxy=False,
        performance=dict(seconds=time.perf_counter()-started,peakCudaMemoryBytes=torch.cuda.max_memory_allocated()))
    atomic_json(args.output,result)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('input','pose-input','target','output','models-root'):p.add_argument('--'+name,required=True)
    p.add_argument('--device',default='cuda:0')
    run(p.parse_args())
