"""Summarize actual schema-4 runs; evaluate mask coverage, never shaft-axis error.

No model is loaded. Annotations are optional and retain their own resized-image
coordinate systems until explicitly mapped to the original rotated video.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def summarize(path):
    result = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if result.get("schemaVersion") != 4:
        raise ValueError(f"Expected schema 4: {path}")
    tracks = {}
    for frame in result["frames"]:
        for obj in frame.get("objects", []):
            identity = obj["objectId"]
            item = tracks.setdefault(identity, dict(athleteIds=set(), states=Counter(), measurementSources=Counter(),
                measurementQuality=Counter(), missingMeasurements=0, proxyMeasurements=0,
                firstTimestamp=frame["timestampSeconds"], lastTimestamp=frame["timestampSeconds"]))
            item["athleteIds"].add(obj["athleteId"])
            item["states"][obj["trackingState"]] += 1
            item["lastTimestamp"] = frame["timestampSeconds"]
            measurement = obj.get("measurement")
            if measurement is None:
                item["missingMeasurements"] += 1
            else:
                item["measurementSources"][measurement["source"]] += 1
                item["measurementQuality"][measurement["quality"]] += 1
                item["proxyMeasurements"] += int(measurement.get("isProxy", False))
    for item in tracks.values():
        item["athleteIds"] = sorted(item["athleteIds"])
    predictions = []
    for prediction in result.get("exercisePredictions", []):
        predictions.append({key: prediction.get(key) for key in ("athleteId", "exercise", "modelExercise", "ownershipGate", "score", "margin", "method", "scoreMeaning")})
        predictions[-1]["windowDecisions"] = dict(Counter(w["decision"] for w in prediction.get("windows", [])))
    summary = dict(result=str(Path(path).resolve()), video=result["video"], frameCount=len(result["frames"]),
        framesWithoutTrackedObject=sum(not any(o["trackingState"] == "Tracked" for o in f.get("objects", [])) for f in result["frames"]),
        athletes=result.get("athletes", []), objects=tracks, exercisePredictions=predictions,
        performance=result.get("visionMetadata", {}).get("performance"),
        performanceScope="vision stage only; excludes preceding pose stage and application analytics",
        provider=result.get("visionMetadata", {}).get("provider"),
        videoHash=result.get("visionMetadata", {}).get("videoHash"))
    return result, summary


def mask_coverage(result, annotation_paths, project_root):
    width, height = result["video"]["width"], result["video"]["height"]
    times = np.asarray([f["timestampSeconds"] for f in result["frames"]])
    rows, skipped = [], []
    verified_videos = {}
    for annotation_path in annotation_paths:
        document = json.loads(Path(annotation_path).read_text(encoding="utf-8-sig"))
        videos = {v["id"]: v for v in document.get("videos", [])}
        for task in document.get("tasks", []):
            video = videos.get(task.get("video_id"))
            if not video or Path(video["path"]).name != result["video"]["fileName"]:
                continue
            source = (project_root/video["path"]).resolve()
            if source not in verified_videos:
                verified_videos[source] = source.is_file() and sha256(source) == result.get("visionMetadata", {}).get("videoHash")
            reason = None
            if not verified_videos[source]:
                reason = "Annotation video path does not match analyzed video SHA256"
            elif video.get("bytes") is not None and source.stat().st_size != video["bytes"]:
                reason = "Annotation video file size changed"
            elif task.get("original_width") != width or task.get("original_height") != height:
                reason = "Annotation original dimensions differ from rotation-corrected result"
            elif not task.get("shaft_segments"):
                reason = "No annotated visible line; negative-frame precision is not inferred"
            elif task.get("shaft_visibility") not in ("visible", "partial"):
                reason = "Annotation is not a visible/partial shaft"
            if reason:
                skipped.append(dict(taskId=task["id"], reason=reason))
                continue
            timestamp = float(task["timestamp"])
            frame_index = int(np.argmin(np.abs(times-timestamp)))
            time_error = abs(float(times[frame_index])-timestamp)
            tolerance = max(.005, .51/max(result["video"]["framesPerSecond"], 1))
            if time_error > tolerance:
                skipped.append(dict(taskId=task["id"], reason="Annotation timestamp has no sufficiently close presentation frame"))
                continue
            sx, sy = width/task["width"], height/task["height"]
            samples = []
            for x1, y1, x2, y2 in task["shaft_segments"]:
                x1, y1, x2, y2 = x1*sx, y1*sy, x2*sx, y2*sy
                length = math.hypot(x2-x1, y2-y1)
                count = max(2, int(math.ceil(length))+1)
                samples.append(np.stack([np.linspace(x1, x2, count), np.linspace(y1, y2, count)], axis=1))
            points = np.rint(np.concatenate(samples)).astype(int)
            if np.any(points[:, 0] < 0) or np.any(points[:, 0] >= width) or np.any(points[:, 1] < 0) or np.any(points[:, 1] >= height):
                skipped.append(dict(taskId=task["id"], reason="Mapped annotation extends outside source image"))
                continue
            union = np.zeros((height, width), np.uint8)
            object_scores = []
            for obj in result["frames"][frame_index].get("objects", []):
                if obj["trackingState"] != "Tracked" or not obj.get("maskPath"):
                    continue
                mask = cv2.imread(obj["maskPath"], cv2.IMREAD_GRAYSCALE)
                if mask is None or mask.shape != (height, width):
                    raise ValueError(f"Missing/mismatched mask artifact {obj['maskPath']}")
                binary = (mask > 0).astype(np.uint8)
                union |= binary
                object_scores.append(dict(objectId=obj["objectId"], athleteId=obj["athleteId"],
                    lineCoverage=float(binary[points[:, 1], points[:, 0]].mean()),
                    maskAreaPixels=int(binary.sum())))
            # Annotation is drawn on a smaller review image; report strict and a
            # separately labelled two-review-pixel tolerance, not hidden dilation.
            radius = max(1, int(math.ceil(2*max(sx, sy))))
            dilated = cv2.dilate(union, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1, 2*radius+1)))
            rows.append(dict(annotationFile=str(Path(annotation_path).resolve()), taskId=task["id"],
                frameIndex=frame_index, timestampSeconds=float(times[frame_index]), annotationTimeErrorSeconds=time_error,
                annotatedPointSamples=len(points), coordinateScale=[sx, sy],
                strictLineCoverage=float(union[points[:, 1], points[:, 0]].mean()),
                tolerantLineCoverage=float(dilated[points[:, 1], points[:, 0]].mean()),
                toleranceOriginalPixels=radius, objects=object_scores))
    weights = np.asarray([r["annotatedPointSamples"] for r in rows])
    available = [r for r in rows if r["objects"]]
    return dict(metric="fraction of visible annotated shaft-line samples inside union of tracked masks",
        interpretation="Coverage only: not mask precision, axis localization error, velocity accuracy or exercise accuracy. Large inaccurate masks may also cover a line.",
        matchedAnnotatedFrames=len(rows), skipped=skipped, frames=rows,
        annotatedFramesWithTrackedMask=len(available),
        lengthWeightedStrictCoverageWhenMaskAvailable=float(np.average([r["strictLineCoverage"] for r in available],
            weights=[r["annotatedPointSamples"] for r in available])) if available else None,
        lengthWeightedStrictCoverage=float(np.average([r["strictLineCoverage"] for r in rows], weights=weights)) if rows else None,
        lengthWeightedTolerantCoverage=float(np.average([r["tolerantLineCoverage"] for r in rows], weights=weights)) if rows else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", nargs="+", required=True)
    parser.add_argument("--annotations", nargs="*", default=[])
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = []
    for path in args.results:
        result, summary = summarize(path)
        if args.annotations:
            summary["annotationMaskCoverage"] = mask_coverage(result, args.annotations, args.project_root)
        reports.append(summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(schema=1, results=reports), indent=2), encoding="utf-8")
    print(json.dumps(dict(report=str(args.output.resolve()),
        videos=[dict(file=r["video"]["fileName"], frames=r["frameCount"], objects=r["objects"],
                     predictions=r["exercisePredictions"], performance=r["performance"],
                     annotatedFrames=r.get("annotationMaskCoverage", {}).get("matchedAnnotatedFrames"),
                     lineCoverage=r.get("annotationMaskCoverage", {}).get("lengthWeightedStrictCoverage")) for r in reports])))


if __name__ == "__main__":
    main()
