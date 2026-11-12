"""CPU-only summary of saved benchmark trajectories; never modifies source results."""
import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "artifacts/model-comparison"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    rows = []
    for name in ("bench", "bench2", "squat", "squat2", "deadlift", "deadlift2"):
        for backend in ("current", "custom"):
            path = SOURCE / f"{name}-{backend}.json"
            result = read(path)
            points = read(SOURCE / "probe-inputs" / (path.name + ".shaft-points.json"))
            segments = []
            for athlete in points:
                for identity, group in itertools.groupby(athlete["points"], lambda p: p["Segment"]):
                    group = list(group)
                    segments.append(dict(athlete=athlete["athlete"], segment=identity,
                        samples=len(group), start=group[0]["Time"], end=group[-1]["Time"]))
            pose_intervals = []
            for athlete in result["athletes"]:
                indexes = [i for i, f in enumerate(result["frames"])
                    if any(a["athleteId"] == athlete["id"] and a["trackingState"] == "Tracked"
                           for a in f["athletes"])]
                if indexes:
                    pose_intervals.append(dict(athlete=athlete["id"], firstFrame=indexes[0],
                        lastFrame=indexes[-1], first=result["frames"][indexes[0]]["timestampSeconds"],
                        last=result["frames"][indexes[-1]]["timestampSeconds"]))
            rows.append(dict(video=name, backend=backend, source=str(path),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), segments=segments,
                trackedPoseExtents=pose_intervals,
                rejections=dict(Counter(o["rejectionReason"] for f in result["frames"]
                    for o in f.get("objects", []) if o.get("rejectionReason"))),
                rawShaftObservations=sum(len(f.get("shafts", [])) for f in result["frames"]),
                ownedShaftObservations=sum(s.get("athleteId") is not None
                    for f in result["frames"] for s in f.get("shafts", []))))
    output = ROOT / "artifacts/rep-diagnosis/saved-baseline-summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
