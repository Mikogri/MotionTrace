"""Compare existing C# analyzer output against locally reviewed phase timestamps."""
import argparse
import json
from pathlib import Path
import statistics

parser = argparse.ArgumentParser()
parser.add_argument("--metrics", required=True)
parser.add_argument("--source", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--manual-exercise", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
annotations = json.loads((root / "research/barbell/phase_annotations.json").read_text(encoding="utf-8-sig"))
truth = next(r for r in annotations["records"] if r["source"] == args.source)["reps"]
predicted = json.loads(Path(args.metrics).read_text(encoding="utf-8-sig"))["shaftReps"]
fields = {"lowering_start": "loweringStart", "lowering_end": "loweringEnd",
          "lifting_start": "liftingStart", "lifting_end": "liftingEnd"}
remaining = set(range(len(truth)))
rows = []
errors = []
for index, rep in enumerate(predicted):
    candidates = [(abs(rep["liftingStart"] - truth[i]["lifting_start"]["time"]), i)
                  for i in remaining if truth[i].get("lifting_start")]
    distance, matched = min(candidates, default=(float("inf"), None))
    if distance > 1.5:
        rows.append(dict(predictedRep=index+1, matchedAnnotation=None))
        continue
    remaining.remove(matched)
    differences = {name: rep[field] - truth[matched][name]["time"]
                   for name, field in fields.items() if rep.get(field) is not None and truth[matched].get(name)}
    errors.extend(abs(value) for value in differences.values())
    rows.append(dict(predictedRep=index+1, matchedAnnotation=matched+1, boundaryErrorSeconds=differences))
report = dict(source=args.source, manualExerciseOverride=args.manual_exercise,
              predictedReps=len(predicted), annotatedReps=len(truth), missedAnnotations=[i+1 for i in sorted(remaining)],
              comparisons=rows, matchedBoundaryMeanAbsoluteErrorSeconds=statistics.mean(errors) if errors else None,
              matchingPolicy="one-to-one nearest lifting start, <=1.5s; errors only for matched boundaries",
              limitation="Mask proxy measurements; missed reps excluded from boundary MAE. No velocity ground truth.")
Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
