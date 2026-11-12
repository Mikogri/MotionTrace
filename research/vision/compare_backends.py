"""CPU comparison against user annotations using the shared C# movement analyzer.

No training or GPU inference. Missing detections remain in coverage denominators.
Unmatched reps are not called false positives: the phase annotations are partial.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess

import cv2
import numpy as np

from evaluate_results import mask_coverage

ROOT = Path(__file__).resolve().parents[2]
FIELDS = {"lowering_start": "loweringStart", "lowering_end": "loweringEnd",
          "lifting_start": "liftingStart", "lifting_end": "liftingEnd"}
EXERCISES = {"bench": "BenchPress", "deadlift": "Deadlift", "squat": "Squat"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def hash_file(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def compare_reps(truth, predicted):
    pairs = []
    for i, expected in enumerate(truth):
        a, b = expected["lifting_start"]["time"], expected["lifting_end"]["time"]
        for j, rep in enumerate(predicted):
            intersection = max(0., min(b, rep["liftingEnd"]) - max(a, rep["liftingStart"]))
            union = max(b, rep["liftingEnd"]) - min(a, rep["liftingStart"])
            if intersection / max(.001, union) >= .2:
                pairs.append((intersection / union, i, j))
    used_truth, used_predictions, matches, errors = set(), set(), [], []
    for overlap, i, j in sorted(pairs, reverse=True):
        if i in used_truth or j in used_predictions:
            continue
        used_truth.add(i)
        used_predictions.add(j)
        boundary_errors = {name: predicted[j][field] - truth[i][name]["time"]
            for name, field in FIELDS.items() if truth[i].get(name) and predicted[j].get(field) is not None}
        errors.extend(abs(error) for error in boundary_errors.values())
        durations = {}
        for phase in ("lowering", "lifting"):
            if truth[i].get(phase + "_start") and truth[i].get(phase + "_end"):
                expected_duration = truth[i][phase + "_end"]["time"] - truth[i][phase + "_start"]["time"]
                if predicted[j].get(phase) is not None:
                    durations[phase] = dict(referenceSeconds=expected_duration,
                        predictedSeconds=predicted[j][phase], errorSeconds=predicted[j][phase] - expected_duration)
        if all(truth[i].get(field) and predicted[j].get(mapped) is not None for field, mapped in FIELDS.items()):
            after_lift = truth[i]["lowering_start"]["time"] >= truth[i]["lifting_end"]["time"]
            pause_a, pause_b = ("lifting_end", "lowering_start") if after_lift else ("lowering_end", "lifting_start")
            expected_pause = truth[i][pause_b]["time"] - truth[i][pause_a]["time"]
            predicted_pause = predicted[j][FIELDS[pause_b]] - predicted[j][FIELDS[pause_a]]
            durations["pauseAfterLift" if after_lift else "bottomPause"] = dict(
                referenceSeconds=expected_pause, predictedSeconds=predicted_pause,
                errorSeconds=predicted_pause - expected_pause)
            expected_total = max(truth[i]["lowering_end"]["time"], truth[i]["lifting_end"]["time"]) - min(
                truth[i]["lowering_start"]["time"], truth[i]["lifting_start"]["time"])
            predicted_total = max(predicted[j]["loweringEnd"], predicted[j]["liftingEnd"]) - min(
                predicted[j]["loweringStart"], predicted[j]["liftingStart"])
            durations["rep"] = dict(referenceSeconds=expected_total, predictedSeconds=predicted_total,
                errorSeconds=predicted_total - expected_total)
        matches.append(dict(annotationRep=i + 1, predictedRep=j + 1, athlete=predicted[j]["athlete"],
            liftIntersectionOverUnion=overlap, boundaryErrorsSeconds=boundary_errors, durations=durations))
    return dict(annotatedReps=len(truth), detectedReps=len(predicted), matchedReps=len(matches),
        missingAnnotationReps=[i + 1 for i in range(len(truth)) if i not in used_truth],
        unmatchedDetections=[dict(index=j + 1, **p) for j, p in enumerate(predicted) if j not in used_predictions],
        matchedBoundaryCount=len(errors), matchedBoundaryMaeSeconds=statistics.mean(errors) if errors else None,
        annotatedBoundaryCount=sum(bool(rep.get(field)) for rep in truth for field in FIELDS),
        matches=matches, policy="greedy highest lift interval IoU >=0.2, one-to-one; MAE excludes missed reps",
        falsePositiveLimitation="Unmatched detections need review; phase annotations do not guarantee exhaustive negative labels")


def custom_line_coverage(result, annotation_paths):
    width, height = result["video"]["width"], result["video"]["height"]
    times = np.array([f["timestampSeconds"] for f in result["frames"]])
    rows = []
    for path in annotation_paths:
        document = read(path)
        videos = {v["id"]: v for v in document["videos"]}
        for task in document["tasks"]:
            video = videos[task["video_id"]]
            if Path(video["path"]).name != result["video"]["fileName"]:
                continue
            if task.get("shaft_visibility") not in ("visible", "partial") or not task.get("shaft_segments"):
                continue
            if (task["original_width"], task["original_height"]) != (width, height):
                raise ValueError("Annotation dimensions do not match result")
            index = int(np.argmin(np.abs(times - task["timestamp"])))
            error = abs(times[index] - task["timestamp"])
            if error > max(.005, .51 / result["video"]["framesPerSecond"]):
                continue
            sx, sy = width / task["width"], height / task["height"]
            points = []
            for x1, y1, x2, y2 in task["shaft_segments"]:
                a, b = np.array([x1 * sx, y1 * sy]), np.array([x2 * sx, y2 * sy])
                points.append(np.linspace(a, b, max(2, int(np.ceil(np.linalg.norm(b - a))) + 1)))
            points = np.concatenate(points)
            frame = result["frames"][index]
            shafts = frame.get("shafts") or ([frame["shaft"]] if frame.get("shaft") else [])
            segments = [s for shaft in shafts for s in shaft["segments"]]
            distances = np.full(len(points), np.inf)
            for segment in segments:
                a = np.array([segment["x1"], segment["y1"]])
                b = np.array([segment["x2"], segment["y2"]])
                direction = b - a
                t = np.clip((points - a) @ direction / max(1e-9, direction @ direction), 0., 1.)
                distances = np.minimum(distances, np.linalg.norm(points - a - t[:, None] * direction, axis=1))
            rows.append(dict(taskId=task["id"], pointSamples=len(points), segments=len(segments),
                annotatedTimeErrorSeconds=float(error), toleranceOriginalPixels=2 * max(sx, sy),
                lineCoverageWithinTwoReviewPixels=float(np.mean(distances <= 2 * max(sx, sy))),
                meanDistancePixelsWhenDetected=float(np.mean(distances)) if segments else None))
    return dict(annotatedFrames=len(rows), framesWithDetectedSegments=sum(r["segments"] > 0 for r in rows),
        lengthWeightedCoverageWithinTwoReviewPixels=float(np.average(
            [r["lineCoverageWithinTwoReviewPixels"] for r in rows], weights=[r["pointSamples"] for r in rows])) if rows else None,
        frames=rows, limitation="Distance to detected visible segments, not physical point error. Different metric than SAM mask coverage; no mask precision inferred.")


def training_split(source):
    document = read(ROOT / "research/barbell/training_annotations.json")
    matches = [v for v in document["videos"] if v["path"] == source]
    if not matches:
        return "not in deployed shaft-v1 training/validation/test (squat/deadlift candidate is separate, not deployed)"
    tasks = {t["id"] for t in document["tasks"] if t["video_id"] == matches[0]["id"]}
    splits = read(ROOT / "artifacts/shaft_model/split.json")
    return ", ".join(key for key, ids in splits.items() if tasks.intersection(ids))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/model-comparison")
    parser.add_argument("--snapshots", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    probe = ROOT / "research/barbell/AnalysisProbe"
    subprocess.run(["dotnet", "build", str(probe), "--nologo", "-v:q"], check=True)
    dll = probe / "bin/Debug/net10.0/AnalysisProbe.dll"
    records = read(ROOT / "research/barbell/phase_annotations.json")["records"]
    annotation_paths = [ROOT / "research/barbell/training_annotations.json", ROOT / "research/barbell/squat_deadlift_annotations.json"]
    names = {"0c1164c17f6b": "bench", "743f1c564875": "squat", "f5050fa1e2ce": "deadlift",
             "e2ac63dba866": "bench2", "37aed827c9b3": "squat2", "b93628934545": "deadlift2"}
    reports = []
    for record in records:
        name = names.get(record["video_id"])
        if not name:
            continue
        for backend in ("custom", "current"):
            path = args.output / f"{name}-{backend}.json"
            if args.snapshots:
                if name.endswith("2"):
                    continue
                path = ROOT / "artifacts/tracking-v3-final-production" / (record["video_id"] + ".json") if backend == "custom" else ROOT / "artifacts/vision-validation" / (name + ("-guarded.json" if name == "squat" else "-final.json"))
            result = read(path)
            # AnalysisProbe saves a trajectory sidecar, so work on copies and preserve source artifacts.
            metrics_input = args.output / "probe-inputs" / (name + "-" + backend + ".json")
            metrics_input.parent.mkdir(exist_ok=True)
            shutil.copyfile(path, metrics_input)
            call = subprocess.run(["dotnet", str(dll), str(metrics_input), EXERCISES[record["exercise"]]],
                check=True, capture_output=True, text=True, encoding="utf-8")
            metrics = json.loads(call.stdout[call.stdout.index("{"):])
            (args.output / f"{name}-{backend}-metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
            entry = dict(video=record["source"], backend=backend, snapshot=args.snapshots,
                result=str(path.resolve()), resultHash=hash_file(path), videoHash=hash_file(ROOT / record["source"]),
                customTrainingSplit=training_split(record["source"]),
                manualExercise=EXERCISES[record["exercise"]],
                phases=compare_reps(record["reps"], metrics["shaftReps"]),
                performance=result.get("visionMetadata", {}).get("performance") if backend == "current" else result.get("performance"),
                predictions=result.get("exercisePredictions", []),
                shaftSamples=metrics["shaftSamples"],
                modelProvenance=result.get("comparisonMetadata", result.get("versions")))
            if backend == "current":
                entry["annotationMaskCoverage"] = mask_coverage(result, annotation_paths, ROOT)
            else:
                entry["annotationLineCoverage"] = custom_line_coverage(result, annotation_paths)
            reports.append(entry)
    report = dict(results=reports,
        annotationHashes={str(p.relative_to(ROOT)): hash_file(p) for p in
            [ROOT / "research/barbell/phase_annotations.json", *annotation_paths]},
        analyzerSourceHashes={str(p.relative_to(ROOT)): hash_file(p) for p in sorted(
            (ROOT / "src/MotionTrace.Core/Motion").glob("*.cs"))},
        limitations=[
        "Manual exercise override for both backends isolates trajectory/phase quality, not end-to-end automatic classification.",
        "Phase labels were used during earlier detector threshold development; this is a development regression benchmark.",
        "No reference metric velocities or consistently annotated physical measurement points: no m/s accuracy claimed.",
        "User shaft annotations describe visible lines, not segmentation masks. Mask coverage and segment-distance coverage are different metrics.",
        "Phase labels are not exhaustive: unmatched detections are unverified, not automatically false positives."])
    destination = args.output / ("snapshot-report.json" if args.snapshots else "report.json")
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps([dict(video=r["video"], backend=r["backend"], phases=r["phases"], split=r["customTrainingSplit"]) for r in reports]))


if __name__ == "__main__":
    main()
