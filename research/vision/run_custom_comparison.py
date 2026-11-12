"""Run all six custom-model comparison jobs sequentially after GPU is free."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
NAMES = {"0c1164c17f6b": "bench", "743f1c564875": "squat", "f5050fa1e2ce": "deadlift",
         "e2ac63dba866": "bench2", "37aed827c9b3": "squat2", "b93628934545": "deadlift2"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/model-comparison")
    parser.add_argument("--weights", type=Path, default=ROOT / "ai/models/shaft-v1.pt")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    records = json.loads((ROOT / "research/barbell/phase_annotations.json").read_text(encoding="utf-8"))["records"]
    runs = []
    for record in records:
        name = NAMES[record["video_id"]]
        pose = ROOT / "artifacts/tracking-v3-final-production" / (record["video_id"] + ".json") if name.endswith("2") else ROOT / "artifacts/vision-validation" / (name + ("-guarded.json" if name == "squat" else "-final.json"))
        command = [sys.executable, str(ROOT / "research/vision/replay_custom.py"),
                   "--input", str(ROOT / record["source"]), "--pose-input", str(pose),
                   "--output", str(out / (name + "-custom.json")), "--weights", str(args.weights.resolve())]
        started = time.perf_counter()
        with (out / (name + "-custom.log")).open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, check=True)
        runs.append(dict(name=name, command=command, wallSeconds=time.perf_counter() - started))
        (out / "custom-runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
        print(json.dumps(runs[-1]), flush=True)


if __name__ == "__main__":
    main()
