"""Evaluate the real bench reruns without overwriting earlier comparison evidence."""
import json
import shutil
import subprocess
from pathlib import Path

from compare_backends import ROOT, compare_reps, hash_file, read

out = ROOT / "artifacts/continuity-repair"
truth = next(r for r in read(ROOT / "research/barbell/phase_annotations.json")["records"]
             if r["video_id"] == "0c1164c17f6b")
probe = ROOT / "artifacts/model-candidate-comparison/baseline-probe/AnalysisProbe.dll"
results = []
for label, path in [
    ("current-before", ROOT / "artifacts/model-comparison/bench-current.json"),
    ("v1-before", ROOT / "artifacts/model-comparison/bench-custom.json"),
    ("v2-before", ROOT / "artifacts/model-candidate-comparison/bench-custom.json"),
    ("current-after", out / "bench-current.json"),
    ("v1-after", out / "bench-custom.json"),
    ("v2-after", out / "bench-candidate.json"),
]:
    copied = out / "probe-inputs" / path.parent.name / path.name
    copied.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, copied)
    call = subprocess.run(["dotnet", str(probe), str(copied), "BenchPress"],
                          check=True, capture_output=True, text=True, encoding="utf-8")
    metrics = json.loads(call.stdout[call.stdout.index("{"):])
    (out / (label + "-metrics.json")).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    result = read(path)
    results.append(dict(label=label, source=str(path), sourceHash=hash_file(path),
                        phases=compare_reps(truth["reps"], metrics["shaftReps"]),
                        samples=metrics["shaftSamples"], athletes=result["athletes"],
                        predictions=result.get("exercisePredictions", [])))
report = dict(results=results, annotationHash=hash_file(ROOT / "research/barbell/phase_annotations.json"),
              limitation="Development regression on one training video. Fresh pose inference after identity fix; same baseline C# analyzer and manual BenchPress for all variants.")
(out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps([dict(label=r["label"], matched=r["phases"]["matchedReps"],
                       missing=r["phases"]["missingAnnotationReps"],
                       mae=r["phases"]["matchedBoundaryMaeSeconds"]) for r in results], indent=2))
