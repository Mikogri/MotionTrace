"""Replay the production custom shaft pipeline on an explicitly shared pose input.

Evaluation only: does not alter the application provider or its model weights.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--pose-input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--weights", type=Path, default=ROOT / "ai/models/shaft-v1.pt")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    import cv2
    import torch
    from motiontrace_ai.focused_shaft import FocusedShaftDetector
    from motiontrace_ai.multi_shaft_tracking import MultiShaftTracker
    from motiontrace_ai.shaft_model import ShaftDetector
    from motiontrace_ai.shaft_ownership import ShaftOwnership
    from motiontrace_ai.video_decode import VideoDecoder, PrefetchedVideoDecoder

    torch.set_num_threads(4)
    cv2.setNumThreads(2)
    pose = json.loads(args.pose_input.read_text(encoding="utf-8-sig"))
    expected_hash = pose.get("videoHash") or pose.get("visionMetadata", {}).get("videoHash")
    source_hash = digest(args.input)
    if expected_hash and expected_hash != source_hash:
        raise ValueError("Pose input belongs to a different video")
    weights = args.weights
    started = time.perf_counter()
    detector = FocusedShaftDetector(ShaftDetector(weights, "cuda:0"))
    tracker, ownership = MultiShaftTracker(detector), ShaftOwnership()
    capture = VideoDecoder(args.input)
    if capture.width * capture.height >= 3840 * 2160:
        capture = PrefetchedVideoDecoder(args.input, decoder=capture)
    previous, frames = [], []
    try:
        for index, (timestamp, image) in enumerate(capture):
            original = pose["frames"][index]
            if abs(timestamp - original["timestampSeconds"]) > 1e-8:
                raise ValueError("Presentation timestamps do not match shared poses")
            poses = original["athletes"]
            detector.prepare(timestamp, poses, previous)
            shafts = tracker.update(image, timestamp, poses)
            ownership.update(timestamp, shafts, poses, capture.height)
            frames.append(dict(timestampSeconds=timestamp, athletes=poses, shafts=shafts))
            previous = shafts
        if len(frames) != len(pose["frames"]):
            raise ValueError("Decoded frame count differs from shared poses")
        ownership.complete_gaps(frames, capture.height)
    finally:
        capture.close()
    confirmed = {a["id"] for a in pose["athletes"]}
    for frame in frames:
        for shaft in frame["shafts"]:
            if shaft["athleteId"] not in confirmed:
                shaft["athleteId"] = None
    elapsed = time.perf_counter() - started
    if digest(args.input) != source_hash:
        raise ValueError("Source video changed during custom comparison")
    result = dict(schemaVersion=3, provider="custom_barbell", video=pose["video"],
        frames=frames, athletes=[dict(id=i, displayName=f"Athlete {i}",
            isExerciseParticipant=i in ownership.participants) for i in sorted(confirmed)],
        performance=dict(elapsedSeconds=elapsed, scope="custom model setup, video decode, shaft detection/tracking/ownership; excludes cached pose inference"),
        focusedDetection=detector.statistics,
        comparisonMetadata=dict(videoHash=source_hash, poseInput=str(args.pose_input.resolve()),
            poseInputHash=digest(args.pose_input), modelHash=digest(weights),
            sourceHashes={p.name: digest(p) for p in sorted((ROOT / "ai/motiontrace_ai").glob("*.py"))}),
        versions={**pose["versions"], "engineVersion": "custom-comparison-replay-1",
            "barbellModelVersion": digest(weights), "barbellProvider": "custom_barbell",
            "trackerVersion": MultiShaftTracker.VERSION},
        limitations=["Research replay using shared cached poses. Custom shaft geometry is not calibrated metric velocity."])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(dict(output=str(args.output), frames=len(frames), seconds=elapsed)))


if __name__ == "__main__":
    main()
