"""Shared pose/target/exercise preparation. No tracker result is used as another's input."""
import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision.analyze import atomic_json
from vision.cache import file_digest
from motiontrace_ai.video_decode import validate_analysis_frames, VideoDecoder


def delayed_owner(pose, index, x, y):
    """A rack may be marked before anybody enters the frame.

    Require sustained, confident proximity and a unique candidate throughout
    the clip. Never resolve competing lifters by their order of appearance.
    """
    starts = {}
    candidates = set()
    for frame in pose['frames'][index:]:
        near = set()
        for person in frame['athletes']:
            wrists = [k for k in person['keypoints']
                      if k['joint'] in ('LeftWrist', 'RightWrist') and k['confidence'] >= .65]
            if (person['trackingState'] == 'Tracked' and wrists
                    and min(math.hypot(x-k['x'], y-k['y']) for k in wrists) <= pose['video']['height']*.15):
                near.add(person['athleteId'])
        starts = {owner: starts.get(owner, frame['timestampSeconds']) for owner in near}
        for owner, start in starts.items():
            if frame['timestampSeconds']-start >= .5:
                candidates.add(owner)
    return next(iter(candidates)) if len(candidates) == 1 else None


def resolve_target(pose, target):
    validate_analysis_frames(pose)
    target = dict(target)
    two_points = 'points' in target
    if two_points:
        from comparison.tap_backends import target_points
        points = target_points(target)
        for p in points:
            if (not isinstance(p, dict) or any(isinstance(p.get(k),bool) or not isinstance(p.get(k),(int,float)) or not math.isfinite(p[k]) for k in ('x','y'))
                    or not 0 <= p['x'] < pose['video']['width'] or not 0 <= p['y'] < pose['video']['height']):
                raise ValueError('Both physical points must be finite and inside the video')
        # Midpoint is used ONLY to associate pose context; the tracker receives
        # the two unchanged physical queries, never this inferred coordinate.
        point = {k:sum(p[k] for p in points)/2 for k in ('x','y')}
    else:
        point = target.get('point')
    if not isinstance(point, dict) or any(isinstance(point.get(k),bool) or not isinstance(point.get(k), (int,float)) or not math.isfinite(point[k]) for k in ('x','y')):
        raise ValueError('Mark a visible bar end / plate axis before comparing trackers; a box center is not a physical target.')
    video = pose['video']; x,y = point['x'],point['y']
    if not 0 <= x < video['width'] or not 0 <= y < video['height']:
        raise ValueError('Reference point lies outside the source video')
    timestamp = target.get('timestampSeconds',0)
    if isinstance(timestamp,bool) or not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp) or not 0 <= timestamp < video['durationSeconds']:
        raise ValueError('Invalid initialization timestamp')
    index = min(range(len(pose['frames'])), key=lambda i: abs(pose['frames'][i]['timestampSeconds']-timestamp))
    people = [p for p in pose['frames'][index]['athletes'] if p['trackingState']=='Tracked']
    owner = target.get('athleteTrackId',0)
    if isinstance(owner,bool) or not isinstance(owner,int) or owner<0:
        raise ValueError('Athlete identity must be a nonnegative integer')
    if owner:
        if not any(p['id']==owner for p in pose['athletes']):
            raise ValueError('The manually selected athlete is not present in this analysis.')
    else:
        distances=[]
        for p in people:
            wrists=[k for k in p['keypoints'] if k['joint'] in ('LeftWrist','RightWrist') and k['confidence']>=.4]
            if wrists:
                distances.append((min(math.hypot(x-k['x'],y-k['y']) for k in wrists),p['athleteId']))
        distances.sort()
        if not people:
            owner = delayed_owner(pose, index, x, y)
        elif distances and distances[0][0] <= video['height']*.3 and (len(distances)==1 or distances[1][0]-distances[0][0] >= video['height']*.03):
            owner = distances[0][1]
        if not owner:
            if not two_points:
                raise ValueError('Reference-point owner is ambiguous. Select the athlete explicitly or mark a clearer frame.')
            owner = max((p['id'] for p in pose['athletes']), default=0) + 1
            pose['athletes'].append(dict(id=owner,displayName='Marked barbell',isExerciseParticipant=True))
            target['syntheticOwner'] = True
    box=target.get('box')
    if box is not None:
        if (not isinstance(box,dict) or any(isinstance(box.get(k),bool) or not isinstance(box.get(k),(int,float)) or not math.isfinite(box[k]) for k in ('x','y','width','height'))
            or box['width']<=0 or box['height']<=0 or box['x']<0 or box['y']<0
            or box['x']+box['width']>video['width'] or box['y']+box['height']>video['height']
            or not box['x']<=x<=box['x']+box['width'] or not box['y']<=y<=box['y']+box['height']):
            raise ValueError('Target box must be inside the video and contain the selected physical point')
    target.update(targetId=target.get('targetId') or 'bar-reference', athleteTrackId=owner,
                  frameIndex=index,timestampSeconds=pose['frames'][index]['timestampSeconds'],initializationVersion=2 if two_points else 1)
    return target


def classification_key(args, owner, manifest, source_root=None):
    root = Path(source_root) if source_root else Path(__file__).resolve().parents[1]
    sources = [root/'comparison/prepare.py', *sorted((root/'vision').glob('*.py')),
               root/'motiontrace_ai/video_decode.py']
    packages = {}
    for name in ('torch', 'transformers', 'numpy', 'opencv-python', 'av'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    identity = dict(video=file_digest(args.input), pose=file_digest(args.pose_input),
                    owner=owner, device=args.device, model=manifest['models']['xclip'],
                    packages=packages, sources={str(p.relative_to(root)):file_digest(p) for p in sources})
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def cached_classification(path, key, classify):
    """Publish only a complete, byte-verified prediction list; corrupt caches rerun."""
    def digest(predictions):
        return hashlib.sha256(json.dumps(predictions, sort_keys=True, allow_nan=False).encode()).hexdigest()
    try:
        cached = json.loads(path.read_text(encoding='utf-8'))
        if (cached['key'] == key and isinstance(cached['predictions'], list)
                and cached['sha256'] == digest(cached['predictions'])):
            return cached['predictions']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    predictions = classify()
    atomic_json(path, dict(key=key, predictions=predictions, sha256=digest(predictions)))
    return predictions


def run(args):
    import torch
    from vision.pipeline import classify_exercises, verify_manifest
    torch.set_num_threads(4)
    pose=json.loads(Path(args.pose_input).read_text(encoding='utf-8-sig'))
    target=resolve_target(pose,json.loads(Path(args.target).read_text(encoding='utf-8-sig')))
    root=Path(args.models_root)
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8-sig'))
    two_points = 'points' in target
    if not target.get('syntheticOwner'):
        verify_manifest(root,manifest,names=('xclip',) if two_points else ('xclip','grounding_dino'))
    protocol=sys.stdout
    def report(fraction,message):
        print(json.dumps(dict(stage=message,fraction=fraction)),file=protocol,flush=True)
    with contextlib.redirect_stdout(sys.stderr):
        if not two_points and target.get('box') is None:
            from vision.models import GroundingDetector, release_model
            decoder=VideoDecoder(args.input,materialize=lambda i,t:i==target['frameIndex'])
            detector=None
            try:
                detector=GroundingDetector(root/'grounding_dino',args.device)
                for i,(_,image) in enumerate(decoder):
                    if i!=target['frameIndex']:continue
                    x,y=target['point']['x'],target['point']['y']
                    proposals=[c for c in detector.detect(image) if c['box'][0]<=x<=c['box'][2] and c['box'][1]<=y<=c['box'][3]]
                    proposals.sort(key=lambda c:('barbell' in c['label'],c['score']),reverse=True)
                    if not proposals:
                        raise ValueError('No object box contains the physical point. Draw a box around the intended barbell and analyze again.')
                    x1,y1,x2,y2=proposals[0]['box']
                    target['box']=dict(x=x1,y=y1,width=x2-x1,height=y2-y1)
                    target['boxSource']='grounding-dino-proposal'
                    break
            finally:
                decoder.close()
                if detector is not None:release_model(detector)
        # Manual target confirmation authorizes classification of this person;
        # these context rows are NOT tracking observations and are never persisted as such.
        contexts=[[dict(athleteId=target['athleteTrackId'],trackingState='Tracked')] for _ in pose['frames']]
        def classify():
            return classify_exercises(args.input,pose['frames'],{},root,args.device,report,contexts)
        if target.get('syntheticOwner'):
            predictions = []
        elif two_points and getattr(args, 'cache', None):
            # Only the resolved owner reaches X-CLIP; moving either query point
            # without changing that owner must not rerun the same classification.
            key = classification_key(args, target['athleteTrackId'], manifest)
            predictions = cached_classification(Path(args.cache)/'classification'/(key+'.json'), key, classify)
        else:
            predictions = classify()
    pose['exercisePredictions']=predictions
    pose['sharedPreparation']=dict(target=target,classification='unknown-no-pose-owner' if target.get('syntheticOwner') else 'xclip-once-manual-target-owner',models=manifest['models'].get('xclip'))
    atomic_json(args.resolved_target,target)
    atomic_json(args.output,pose)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('input','pose-input','target','resolved-target','output','models-root'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--device',default='cuda:0')
    parser.add_argument('--cache',default=None)
    run(parser.parse_args())
