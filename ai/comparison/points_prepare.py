"""Points-only preparation for two-point tracking (TrainFlow): no pose model, no exercise classification.

Writes the same shared timeline and resolved target files as prepare.py, but the timeline has no athletes: the two
marked points belong to a synthetic "Marked barbell" owner, and only their motion is measured afterwards.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision.analyze import atomic_json
from motiontrace_ai.video_decode import VideoDecoder, validate_analysis_frames
from comparison.prepare import resolve_target


def timeline(path):
    """Frame timestamps and video facts only; no frame is decoded into an image."""
    decoder = VideoDecoder(path, materialize=lambda index, timestamp: False)
    try:
        frames, previous = [], -1.
        for timestamp, _ in decoder:
            frames.append(dict(timestampSeconds=timestamp, athletes=[], shafts=[]))
            previous = timestamp
        if not frames:
            raise ValueError('No video frames decoded')
        return dict(schemaVersion=3,
                    video=dict(fileName=Path(path).name, durationSeconds=decoder.end, finalFrameDurationSeconds=decoder.end-previous,
                               width=decoder.width, height=decoder.height, framesPerSecond=decoder.fps),
                    versions=dict(engineVersion='points-only', poseModelVersion='not-used-points-only'), athletes=[], frames=frames,
                    limitations=['Points only: the lifter is not detected and the exercise is not classified.'])
    finally:
        decoder.close()


def run(args):
    shared = timeline(args.input)
    validate_analysis_frames(shared)
    target = json.loads(Path(args.target).read_text(encoding='utf-8-sig'))
    if 'points' not in target:
        raise ValueError('Points-only preparation needs two marked points')
    # The caller sends the size of the frame the points were marked on; this read of the video replaces a separate probe.
    video = shared['video']
    expected = (target.pop('videoWidth', None), target.pop('videoHeight', None))
    if all(isinstance(v, int) and not isinstance(v, bool) for v in expected) and expected != (video['width'], video['height']):
        raise ValueError('Selected frame dimensions do not match the decoded video.')
    timestamp = target.get('timestampSeconds')
    if isinstance(timestamp, (int, float)) and video['durationSeconds'] and timestamp >= video['durationSeconds']:
        raise ValueError('Selected timestamp is outside the video.')
    # With no athletes in the timeline the points get the synthetic "Marked barbell" owner.
    target = resolve_target(shared, target)
    shared['exercisePredictions'] = []
    shared['sharedPreparation'] = dict(target=target, classification='points-only', models=None)
    atomic_json(args.resolved_target, target)
    atomic_json(args.output, shared)
    print(json.dumps(dict(stage='Points-only preparation', fraction=1)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('input', 'target', 'resolved-target', 'output'):
        parser.add_argument('--'+name, required=True)
    run(parser.parse_args())
