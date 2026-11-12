"""Research-only capture of real detector observations for deterministic tracker replay."""
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai"))
from motiontrace_ai.person_tracking import PersonTracker

original = PersonTracker.update
rows = []


def record(self, detections, timestamp):
    rows.append(dict(time=timestamp, detections=detections,
                     tracks=[dict(vars(t)) for t in self.tracks]))
    return original(self, detections, timestamp)


PersonTracker.update = record
try:
    sys.argv = [str(ROOT / "ai/analyze.py"), *sys.argv[1:]]
    runpy.run_path(sys.argv[0], run_name="__main__")
finally:
    (ROOT / "artifacts/continuity-repair/bench-detections.json").write_text(json.dumps(rows), encoding="utf-8")
