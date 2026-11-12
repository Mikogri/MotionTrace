"""Explicit local real-model validation. Runs GPU jobs sequentially; no legacy shaft inference."""
import json
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[2]
home = Path.home()
pose = str(home / "miniconda3/envs/motiontrace/python.exe")
vision = str(home / "miniconda3/envs/motiontrace-vision/python.exe")
models = str(root / ".models/vision")
output = root / "artifacts/vision-validation"
output.mkdir(parents=True, exist_ok=True)
shared = ["--cache", "artifacts/vision-end-to-end-cache", "--vision-python", vision, "--models-root", models]
jobs = [
    ("offline", [vision, "scripts/test_vision_offline.py", "--models-root", models,
        "--video", "videos/bench/100kg x 5.mp4", "--output", "artifacts/vision-validation/offline.json"]),
    ("bench-final", [vision, "ai/vision/analyze.py", "--models-root", models,
        "--input", "videos/bench/100kg x 5.mp4", "--pose-input", "artifacts/vision-pose-only.json",
        "--output", "artifacts/vision-validation/bench-final.json", "--cache", "artifacts/vision-integration-cache"]),
    ("deadlift-final", [pose, "ai/pipeline.py", "--input", "videos/deadlift/VID_20260214_210811~2 (1).mp4",
        "--output", "artifacts/vision-validation/deadlift-final.json", *shared]),
    ("squat-final", [pose, "ai/pipeline.py", "--input", "videos/squat/VID_20260420_175856~2.mp4",
        "--output", "artifacts/vision-validation/squat-final.json", *shared]),
    ("no-lift-csharp", ["dotnet", "run", "--project", "tests/MotionTrace.Smoke/MotionTrace.Smoke.csproj", "--",
        "artifacts/vision-validation/no-lift.mp4", "ai/pipeline.py", "artifacts/vision-validation/csharp-engine"]),
    ("cancel-csharp", ["dotnet", "run", "--project", "tests/MotionTrace.Smoke/MotionTrace.Smoke.csproj", "--", "--cancel-only",
        "videos/deadlift/VID_20260214_210811~2 (1).mp4", "ai/pipeline.py", "artifacts/vision-end-to-end-cache-cancel"]),
]
records = []
for name, command in jobs:
    started = time.perf_counter()
    print(f"Starting {name}", flush=True)
    with (output / (name + ".log")).open("w", encoding="utf-8") as log, (output / (name + ".stderr.log")).open("w", encoding="utf-8") as error:
        completed = subprocess.run(command, cwd=root, stdout=log, stderr=error)
    records.append(dict(name=name, exitCode=completed.returncode, elapsedSeconds=time.perf_counter()-started, command=command))
    (output / "runs.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Completed {name}: exit {completed.returncode}, {records[-1]['elapsedSeconds']:.1f}s", flush=True)
    if completed.returncode:
        raise SystemExit(completed.returncode)
