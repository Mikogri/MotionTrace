"""Evaluate the candidate replay with a preserved baseline analyzer; never deploy it."""
import json
from pathlib import Path
import shutil
import subprocess

from compare_backends import ROOT, EXERCISES, read, hash_file, compare_reps, custom_line_coverage
from run_custom_comparison import NAMES


def main():
    out = ROOT / "artifacts/model-candidate-comparison"
    baseline = read(ROOT / "artifacts/model-comparison/report.json")
    analyzer_hashes = read(out / "baseline-analyzer-hashes.json")
    if analyzer_hashes != baseline["analyzerSourceHashes"]:
        raise ValueError("Baseline analyzer differs; rerun all backends with a common analyzer")
    records = read(ROOT / "research/barbell/phase_annotations.json")["records"]
    annotations = [ROOT / "research/barbell/training_annotations.json",
                   ROOT / "research/barbell/squat_deadlift_annotations.json"]
    videos = {v["path"]: v["id"] for path in annotations for v in read(path)["videos"]}
    splits = read(ROOT / "artifacts/shaft_multiexercise_v2_run2/split.json")
    entries = []
    for record in records:
        name = NAMES[record["video_id"]]
        path = out / (name + "-custom.json")
        result = read(path)
        target = out / "probe-inputs" / path.name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, target)
        call = subprocess.run(["dotnet", str(out / "baseline-probe/AnalysisProbe.dll"),
                               str(target), EXERCISES[record["exercise"]]],
                              check=True, capture_output=True, text=True, encoding="utf-8")
        metrics = json.loads(call.stdout[call.stdout.index("{"):])
        (out / (name + "-metrics.json")).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        entries.append(dict(video=record["source"], backend="multiexercise-v2-candidate",
            result=str(path), resultHash=hash_file(path),
            candidateTrainingSplit=[k for k, rows in splits.items()
                if any(t["video_id"] == videos[record["source"]] for t in rows)],
            manualExercise=EXERCISES[record["exercise"]],
            phases=compare_reps(record["reps"], metrics["shaftReps"]),
            shaftSamples=metrics["shaftSamples"], performance=result["performance"],
            annotationLineCoverage=custom_line_coverage(result, annotations),
            modelProvenance=result["comparisonMetadata"]))
    report = dict(candidateResults=entries, baselineResults=baseline["results"],
        baselineReportHash=hash_file(ROOT / "artifacts/model-comparison/report.json"),
        analyzerSourceHashes=analyzer_hashes,
        annotationHashes=baseline["annotationHashes"], limitations=baseline["limitations"] + [
            "Candidate videos are train or development validation; no independent held-out final test.",
            "Candidate is a shaft detector, not an exercise classifier. Production weights unchanged."])
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps([dict(video=r["video"], phases=r["phases"], coverage=r["annotationLineCoverage"]["lengthWeightedCoverageWithinTwoReviewPixels"], seconds=r["performance"]["elapsedSeconds"]) for r in entries]))


if __name__ == "__main__":
    main()
