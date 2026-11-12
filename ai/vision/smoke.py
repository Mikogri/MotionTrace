"""Offline real-weight smoke test, including SAM temporal propagation."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import cv2
    import torch
    from motiontrace_ai.video_decode import VideoDecoder
    from vision.models import ExerciseClassifier, GroundingDetector, SamVideoTracker, release_model
    from vision.measurement import MeasurementPoint
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-root", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    torch.set_num_threads(4)
    root = Path(args.models_root)
    report = dict(cuda=torch.cuda.is_available(), torchVersion=torch.__version__, device=args.device, models={})
    start = time.perf_counter()
    decoder = VideoDecoder(args.video)
    samples = []
    try:
        for timestamp, image in decoder:
            samples.append((timestamp, image))
            if len(samples) >= 16:
                break
    finally:
        decoder.close()
    detector = GroundingDetector(root/"grounding_dino", args.device)
    candidates = detector.detect(samples[0][1])
    report["models"]["grounding_dino"] = dict(candidates=candidates, loadedActualWeights=True)
    release_model(detector)
    tracker = SamVideoTracker(root/"sam2", args.device)
    height, width = samples[0][1].shape[:2]
    # A central region is sufficient to test real model execution when the short
    # sample has no barbell. It is not reported as a successful bar detection.
    box = candidates[0]["box"] if candidates else [.25*width, .25*height, .75*width, .75*height]
    tracker.add("smoke-object", 1, (height, width), box=box)
    mask_stats = []
    for index in range(1, min(4, len(samples))):
        values = tracker.track(index, samples[index][1])
        mask, score = values["smoke-object"]
        mask_stats.append(dict(frame=index, pixels=int(mask.sum()), confidence=score))
    report["models"]["sam2"] = dict(frames=mask_stats, loadedActualWeights=True,
        temporalMemoryFrames=len(tracker.session.output_dict_per_obj[0]["non_cond_frame_outputs"]),
        promptSource="dino-candidate" if candidates else "synthetic-smoke-box")
    # Exercise the same late point-correction API as the UI, on this existing
    # object. This automatically chosen test point is not a validated bar axis.
    import numpy as np
    ys, xs = np.nonzero(mask)
    if len(xs):
        middle = len(xs)//2
        point = [float(xs[middle]), float(ys[middle])]
        tracker.add("smoke-object", 4, (height, width), point=point)
        measurement = MeasurementPoint()
        corrected = []
        for index in (4, 5):
            point_mask, confidence = tracker.track(index, samples[index][1])["smoke-object"]
            value = measurement.update(samples[index][1], point_mask, point if index == 4 else None)
            corrected.append(dict(frame=index, confidence=confidence, measurement=value))
        report["models"]["sam2"]["latePointCorrection"] = corrected
        report["models"]["sam2"]["pointNote"] = "Automatically seeded API smoke point, not a manually validated shaft landmark"
    second_box = candidates[1]["box"] if len(candidates) > 1 else [.1*width, .1*height, .3*width, .3*height]
    tracker.add("smoke-second-object", 6, (height, width), box=second_box)
    two_objects = tracker.track(6, samples[6][1])
    propagated = tracker.track(7, samples[7][1])
    if set(two_objects) != {"smoke-object", "smoke-second-object"} or set(propagated) != set(two_objects):
        raise AssertionError("Late second object did not preserve both tracking identities")
    report["models"]["sam2"]["lateSecondObject"] = {identity: int(value[0].sum()) for identity, value in propagated.items()}
    report["models"]["sam2"]["secondObjectNote"] = "Multi-object API test; does not validate athlete ownership"
    release_model(tracker)
    classifier = ExerciseClassifier(root/"xclip", args.device)
    selected = np.linspace(0, len(samples)-1, classifier.num_frames).astype(int)
    prediction = classifier.classify([cv2.cvtColor(samples[index][1], cv2.COLOR_BGR2RGB) for index in selected])
    report["models"]["xclip"] = dict(prediction, loadedActualWeights=True, sampledFrames=classifier.num_frames,
        note="Short execution smoke test, not exercise accuracy evaluation")
    release_model(classifier)
    report["elapsedSeconds"] = time.perf_counter()-start
    report["peakCudaMemoryBytes"] = torch.cuda.max_memory_allocated() if torch.cuda.is_available() else 0
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
