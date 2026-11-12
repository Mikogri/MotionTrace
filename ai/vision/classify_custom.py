"""Optional X-CLIP exercise classification over the custom detector's owned shafts."""
import argparse
import contextlib
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision.analyze import atomic_json, progress
from vision.cache import file_digest
from vision.config import POLICY


def owned_shaft_objects(pose):
    confirmed = {a['id'] for a in pose.get('athletes', []) if a.get('isExerciseParticipant')}
    result = []
    for frame in pose['frames']:
        objects = []
        for shaft in frame.get('shafts', []):
            if shaft.get('athleteId') not in confirmed or shaft.get('ownershipAmbiguous'):
                continue
            segments = shaft.get('segments', [])
            if not segments:
                continue
            xs = [s[key] for s in segments for key in ('x1', 'x2')]
            ys = [s[key] for s in segments for key in ('y1', 'y2')]
            if not all(math.isfinite(v) for v in xs+ys):
                continue
            objects.append(dict(athleteId=shaft['athleteId'], trackingState='Tracked',
                box=dict(x=min(xs), y=min(ys), width=max(1., max(xs)-min(xs)), height=max(1., max(ys)-min(ys)))))
        result.append(objects)
    return result


def classify_result(pose, video, root, device, report):
    from vision.pipeline import classify_exercises
    predictions = classify_exercises(video, pose['frames'], {}, root, device, report, owned_shaft_objects(pose))
    return dict(pose, exercisePredictions=predictions)


def prediction_digest(predictions):
    return hashlib.sha256(json.dumps(predictions, sort_keys=True, allow_nan=False).encode()).hexdigest()


def save_predictions(path, key, predictions):
    atomic_json(path, dict(cacheKey=key, predictions=predictions, sha256=prediction_digest(predictions)))


def load_predictions(path, key):
    try:
        saved = json.loads(Path(path).read_text(encoding='utf-8'))
        if saved['cacheKey'] == key and saved['sha256'] == prediction_digest(saved['predictions']):
            return saved['predictions']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def run(args):
    import torch
    from importlib.metadata import version
    from vision.pipeline import verify_manifest
    started = time.perf_counter()
    torch.set_num_threads(4)
    if args.device.startswith('cuda') and not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable for exercise classification')
    root = Path(args.models_root).resolve()
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8-sig'))
    verify_manifest(root, manifest, names=('xclip',))
    pose = json.loads(Path(args.pose_input).read_text(encoding='utf-8-sig'))
    from motiontrace_ai.video_decode import validate_analysis_frames
    validate_analysis_frames(pose)
    frames = pose.get('frames', [])
    times = [f['timestampSeconds'] for f in frames]
    if not times or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('Custom pose timestamps must be nonempty and increasing')
    source_files = sorted(Path(__file__).parent.glob('*.py'))
    source_files.append(Path(__file__).parents[1]/'motiontrace_ai/video_decode.py')
    identity = dict(videoHash=file_digest(args.input), poseHash=file_digest(args.pose_input),
        model=manifest['models']['xclip'], configuration=POLICY, device=args.device,
        sourceHashes={str(p.relative_to(Path(__file__).parents[1])): file_digest(p) for p in source_files},
        dependencies={name: version(name) for name in ('torch', 'torchvision', 'transformers', 'numpy', 'opencv-python', 'av')})
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache_path = Path(args.cache)/key/'predictions.json'
    predictions = load_predictions(cache_path, key)
    cache_hit = predictions is not None
    if not cache_hit:
        protocol_stdout = sys.stdout
        def report(fraction, message):
            print(json.dumps(dict(type='progress', progress=max(0., (fraction-.75)/.25), message=message)), file=protocol_stdout, flush=True)
        with contextlib.redirect_stdout(sys.stderr):
            predictions = classify_result(pose, args.input, root, args.device, report)['exercisePredictions']
    if file_digest(args.input) != identity['videoHash'] or file_digest(args.pose_input) != identity['poseHash']:
        raise ValueError('Video or custom analysis changed during classification')
    if not cache_hit:
        save_predictions(cache_path, key, predictions)
    result = dict(pose, provider='custom_barbell', exercisePredictions=predictions)
    result['exerciseClassificationMetadata'] = dict(provider='xclip', barbellProvider='custom_barbell',
        status='classified', cacheKey=key, provenance=identity,
        performance=dict(cacheHit=cache_hit, totalSeconds=time.perf_counter()-started))
    atomic_json(args.output, result)
    progress(1., 'Custom barbell analysis and exercise classification ready')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'pose-input', 'output', 'cache', 'models-root'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--device', default='cuda:0')
    run(parser.parse_args())
