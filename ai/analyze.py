"""MotionTrace schema v3. stdout = JSON progress; stderr = framework diagnostics.

All frames are decoded locally. No media is uploaded and no annotated video copy
is created. Cached models must already be installed; weights are never downloaded.
"""
import argparse
import contextlib
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from motiontrace_ai.cache import inference_configuration,pose_fingerprint,cache_key,read_pose_cache,configuration_sources
from motiontrace_ai.person_tracking import PersonTracker
from motiontrace_ai.performance import StageTimings
from motiontrace_ai.video_decode import validate_analysis_frames

ENGINE_VERSION = '0.10.0'
POSE_MODEL = 'rtmpose-m_8xb256-420e_body8-256x192'
POSE_WEIGHTS = 'rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.pth'
DETECTOR_WEIGHTS = 'rtmdet_m_8xb32-100e_coco-obj365-person-235e8209.pth'


def progress(stage, fraction=None):
    message = dict(stage=stage)
    if fraction is not None:
        message['fraction'] = fraction
    print(json.dumps(message), flush=True)


def hash_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as target:
            json.dump(result, target, allow_nan=False, separators=(',', ':'))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def return_cached_analysis(args,path,source,timings,label):
    try:
        with timings.measure('fullCacheRead'):
            result=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(result,dict) or result.get('schemaVersion')!=3 or not isinstance(result.get('frames'),list) or not result['frames']:
            return False
        validate_analysis_frames(result)
        result['video']['fileName']=source.name
    except (OSError,ValueError,KeyError,TypeError):
        return False
    with timings.measure('save'):
        atomic_json(Path(args.output),result)
    progress('Loaded cached analysis',1)
    if getattr(args,'profile_output',None):atomic_json(Path(args.profile_output),timings.snapshot(cache=label,cachedFrames=len(result['frames'])))
    return True


def analyze(args):
    started=time.perf_counter()
    timings=StageTimings()
    progress('Preparing model')
    model = getattr(args, 'pose_model', 'rtmpose-l_8xb256-420e_body8-384x288')
    weights_name = getattr(args, 'pose_weights', '') or (POSE_WEIGHTS if model == POSE_MODEL else 'rtmpose-l_simcc-body7_pt-body7_420e-384x288-3f5a1437_20230504.pth')
    padding = getattr(args, 'crop_padding', .2)
    selected = set(getattr(args, 'athlete_ids', []) or [])
    barbell_provider = getattr(args, 'barbell_provider', 'pose_only')
    with contextlib.redirect_stdout(sys.stderr):
        import cv2
        import torch
        torch.set_num_threads(4)
        cv2.setNumThreads(2)
        if args.device.startswith('cuda') and not torch.cuda.is_available():
            raise RuntimeError('CUDA is unavailable. Select cpu in MotionTrace engine settings.')
        checkpoints = Path(torch.hub.get_dir()) / 'checkpoints'
    pose_weights, detector_weights = checkpoints / weights_name, checkpoints / DETECTOR_WEIGHTS
    for weights in (pose_weights, detector_weights):
        if not weights.is_file():
            raise FileNotFoundError(f'Local model weights missing: {weights}. Install the RTMPose/RTMDet weights first.')
    progress('Checking analysis cache')
    lookup_started=time.perf_counter()
    source=Path(args.input).resolve(strict=True)
    shaft_path=Path(__file__).parent/'models/shaft-v1.pt'
    request=dict(engine=ENGINE_VERSION,model=model,cropPadding=padding,selected=sorted(selected),provider=barbell_provider,
                 tracker=PersonTracker.VERSION,device=args.device,video=hash_file(source),
                 pose=hash_file(pose_weights),detector=hash_file(detector_weights),
                 shaft=hash_file(shaft_path) if barbell_provider=='custom_barbell' and shaft_path.is_file() else 'disabled',
                 packages={p:importlib.metadata.version(p) for p in ('mmpose','mmdet','mmcv','mmengine','torch','torchvision','opencv-python','scipy','av')},
                 adapter={str(p.relative_to(Path(__file__).parent)):hash_file(p)
                          for p in [Path(__file__),*sorted((Path(__file__).parent/'motiontrace_ai').rglob('*.py'))]})
    mmpose_root=Path(importlib.util.find_spec('mmpose').origin).parent
    mmdet_root=Path(importlib.util.find_spec('mmdet').origin).parent
    config_hash=None if Path(model).is_file() else configuration_sources([mmpose_root/'.mim',mmdet_root/'.mim'])
    request_file=Path(args.cache)/'requests'/(cache_key({**request,'configurationSources':config_hash})+'.json') if config_hash else None
    timings.seconds['cacheFingerprint']=time.perf_counter()-lookup_started
    if request_file and request_file.exists():
        try:
            cached_key=json.loads(request_file.read_text(encoding='utf-8'))['cacheKey']
            if isinstance(cached_key,str) and len(cached_key)==64 and all(c in '0123456789abcdef' for c in cached_key):
                if return_cached_analysis(args,Path(args.cache)/(cached_key+'.json'),source,timings,'full-fast'):return
        except (OSError,ValueError,KeyError,TypeError):
            pass
    with contextlib.redirect_stdout(sys.stderr):
        from mmpose.apis import MMPoseInferencer
        detector_config=mmpose_root/'.mim/demo/mmdetection_cfg/rtmdet_m_640-8xb32_coco-person.py'
        inferencer=MMPoseInferencer(pose2d=model,pose2d_weights=str(pose_weights),
                                   det_model=str(detector_config),det_weights=str(detector_weights),
                                   device=args.device,det_cat_ids=[0])

    # StableCrop owns padding; disable the additional default 1.25 pose transform padding.
    for transform in inferencer.inferencer.model.cfg.test_dataloader.dataset.pipeline:
        if transform.get('type') == 'GetBBoxCenterScale':
            transform['padding'] = 1.0
    shaft_path=Path(__file__).parent/'models/shaft-v1.pt'
    shaft_tracker=None
    focused_detector=None
    if barbell_provider=='custom_barbell' and shaft_path.is_file():
        from motiontrace_ai.shaft_model import ShaftDetector
        from motiontrace_ai.multi_shaft_tracking import MultiShaftTracker
        from motiontrace_ai.focused_shaft import FocusedShaftDetector
        focused_detector=FocusedShaftDetector(ShaftDetector(shaft_path,args.device))
        shaft_tracker=MultiShaftTracker(focused_detector)
    timings.seconds['modelSetup']=time.perf_counter()-started-timings.seconds['cacheFingerprint']
    fingerprint={**request,'configuration':inference_configuration(inferencer.inferencer.cfg),
                 'detectorConfiguration':inference_configuration(inferencer.inferencer.detector.cfg)}
    key=cache_key(fingerprint)
    cache_file=Path(args.cache)/(key+'.json')
    if return_cached_analysis(args,cache_file,source,timings,'full'):
        if request_file:atomic_json(request_file,dict(cacheKey=key))
        return

    pose_key=cache_key(pose_fingerprint(fingerprint))
    pose_file=Path(args.cache)/'poses'/(pose_key+'.json')
    with timings.measure('poseCacheRead'):
        cached_poses=read_pose_cache(pose_file,pose_key)
    from motiontrace_ai.video_decode import VideoDecoder,PrefetchedVideoDecoder
    capture = VideoDecoder(source)
    # Benchmarks benefit from overlap at 4K; smaller inputs favor synchronous decoding.
    if not getattr(args,'synchronous_decode',False) and capture.width*capture.height>=3840*2160:
        capture = PrefetchedVideoDecoder(source,decoder=capture)
    try:
        fps,count,width,height=capture.fps,capture.count,capture.width,capture.height
        from motiontrace_ai.pose_pipeline import PosePipeline
        from motiontrace_ai.shaft_ownership import ShaftOwnership
        ownership=ShaftOwnership()
        pose_pipeline=None if cached_poses else PosePipeline(inferencer,padding,selected,timings)
        frames=[]
        previous_shafts=[]
        pose_frames=[]
        index, previous_time = 0, -1.0
        progress('Reusing cached poses' if cached_poses else 'Detecting athletes')
        decode_started=time.perf_counter()
        for timestamp,image in capture:
            timings.seconds['decodeWait']=timings.seconds.get('decodeWait',0)+time.perf_counter()-decode_started
            previous_time = timestamp
            if cached_poses:
                if index>=len(cached_poses['frames']) or abs(cached_poses['frames'][index]['timestampSeconds']-timestamp)>1e-8:
                    pose_file.with_suffix('.sha256.json').unlink(missing_ok=True)
                    raise ValueError('Pose cache timestamps do not match video; invalid cache was discarded. Run analysis again.')
                poses=cached_poses['frames'][index]['athletes']
            else:
                poses=pose_pipeline.update(image,timestamp,width,height)
                pose_frames.append(dict(timestampSeconds=timestamp,athletes=poses))
            shaft_started=time.perf_counter()
            if focused_detector:focused_detector.prepare(timestamp,poses,previous_shafts)
            shafts=shaft_tracker.update(image,timestamp,poses) if shaft_tracker else []
            ownership.update(timestamp,shafts,poses,height)
            previous_shafts=shafts
            timings.seconds['shaft']=timings.seconds.get('shaft',0)+time.perf_counter()-shaft_started
            frames.append(dict(timestampSeconds=timestamp, athletes=poses,shafts=shafts))
            index += 1
            if index % 10 == 0:
                progress('Tracking pose', min(index / count, 0.99) if count > 0 else None)
            decode_started=time.perf_counter()
        if not frames:
            raise ValueError('No video frames decoded')
        if cached_poses and index!=len(cached_poses['frames']):
            pose_file.with_suffix('.sha256.json').unlink(missing_ok=True)
            raise ValueError('Pose cache frame count does not match video; invalid cache was discarded. Run analysis again.')
        confirmed=set(cached_poses['confirmedIds']) if cached_poses else pose_pipeline.tracker.confirmed
        if hasattr(capture,'decode_seconds'):timings.seconds['decodeWorker']=capture.decode_seconds
        progress('Finalizing')
        ownership.complete_gaps(frames,height)
        for frame in frames:
            frame['athletes'] = [p for p in frame['athletes'] if p['athleteId'] in confirmed]
            for shaft in frame['shafts']:
                if shaft['athleteId'] not in confirmed:
                    shaft['athleteId']=None
        result = dict(schemaVersion=3,
                      focusedDetection=focused_detector.statistics if focused_detector else {},
                      performance=timings.snapshot(index),
                      video=dict(fileName=source.name, durationSeconds=capture.end,
                                 finalFrameDurationSeconds=capture.end-previous_time,
                                 width=width, height=height, framesPerSecond=fps),
                      versions=dict(engineVersion=ENGINE_VERSION,
                                    poseModel=model, poseModelVersion=f'{model}:{fingerprint["pose"]}', trackerVersion=PersonTracker.VERSION,
                                    barbellModelVersion=fingerprint['shaft'], detectorModelVersion=fingerprint['detector'],
                                    packages=fingerprint['packages']),
                      athletes=[dict(id=i, displayName=f'Athlete {i}',isExerciseParticipant=barbell_provider=='pose_only' or i in ownership.participants) for i in sorted(confirmed)], frames=frames,
                      limitations=['Conservative box/appearance tracking is not learned ReID. Ambiguous assignments remain Lost. Long occlusions/cuts can create new IDs.',
                                   'Shaft detection is experimental. Temporal person/bar pairing may remain unknown under occlusion or ambiguous motion; manual person selection is available. Optical flow is camera-compensated image motion, not metric velocity.'])
        # A file edited during inference must not create an entry under its old content hash.
        if hash_file(source) != fingerprint['video']:
            raise ValueError('Video changed during analysis. Please run again.')
        save_started=time.perf_counter()
        validate_analysis_frames(result)
        if not cached_poses:
            atomic_json(pose_file,dict(schema=1,confirmedIds=sorted(confirmed),frames=pose_frames))
            atomic_json(pose_file.with_suffix('.sha256.json'),dict(key=pose_key,sha256=hash_file(pose_file)))
        atomic_json(Path(args.output), result)
        atomic_json(cache_file, result)
        if request_file:atomic_json(request_file,dict(cacheKey=key))
        timings.seconds['save']=time.perf_counter()-save_started
        if getattr(args,'profile_output',None):atomic_json(Path(args.profile_output),timings.snapshot(index,cache='pose' if cached_poses else 'miss'))
        progress('Analysis ready', 1)
    finally:
        capture.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--device', default='cuda:0')
    parser.add_argument('--pose-model', default='rtmpose-l_8xb256-420e_body8-384x288')
    parser.add_argument('--pose-weights', default='')
    parser.add_argument('--crop-padding', type=float, default=.2)
    parser.add_argument('--athlete-ids', type=int, nargs='*')
    parser.add_argument('--profile-output')
    parser.add_argument('--synchronous-decode',action='store_true')
    parser.add_argument('--barbell-provider',choices=('pose_only','custom_barbell'),default='pose_only')
    arguments = parser.parse_args()
    try:
        analyze(arguments)
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
