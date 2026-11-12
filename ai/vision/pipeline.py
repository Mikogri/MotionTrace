"""Sequential model stages with original timestamps and bounded image memory."""
import bisect
import hashlib
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np
import torch

from motiontrace_ai.video_decode import VideoDecoder, PrefetchedVideoDecoder
from .config import POLICY
from .geometry import assign_candidates, association_score, box_dict, context_crop, iou, temporal_motion_evidence, confirmed_owner_nearby
from .measurement import MeasurementPoint, torso_contamination
from .models import ExerciseClassifier, GroundingDetector, SamVideoTracker, decide, release_model


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(root, manifest, names=("xclip", "grounding_dino", "sam2")):
    """Detect missing/changed checkpoints before inference or result reuse."""
    for name in names:
        model = manifest.get("models", {}).get(name)
        if not isinstance(model, dict) or not model.get("revision") or not model.get("files"):
            raise ValueError(f"Incomplete model manifest for {name}; run setup-vision.ps1")
        directory = (Path(root)/name).resolve()
        for entry in model["files"]:
            path = (directory/entry["path"]).resolve()
            if not path.is_relative_to(directory):
                raise ValueError(f"Invalid manifest file path for {name}")
            if not path.is_file():
                raise FileNotFoundError(f"Missing local {name} file: {path}; run setup-vision.ps1. Downloads are disabled during analysis.")
            if path.stat().st_size != entry["size"] or file_hash(path) != entry["sha256"]:
                raise ValueError(f"Corrupted or modified {name} file: {path}; reinstall/verify the model with setup-vision.ps1")


def nearest_index(times, timestamp):
    position = bisect.bisect_left(times, timestamp)
    if position == len(times):
        return position-1
    if position and timestamp-times[position-1] <= times[position]-timestamp:
        return position-1
    return position


def load_corrections(path, video_hash, times, width, height, athlete_ids):
    if path is None:
        return {}
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if document.get("videoHash") != video_hash:
        raise ValueError("Object corrections belong to a different video; videoHash does not match")
    result, ownership = {}, {}
    for value in document.get("objects", []):
        object_id, athlete = value["objectId"], value["athleteId"]
        if not isinstance(object_id, str) or not object_id or len(object_id) > 100:
            raise ValueError("Correction objectId must be a nonempty string, at most 100 characters")
        if athlete not in athlete_ids or ownership.get(object_id, athlete) != athlete:
            raise ValueError("Correction athleteId does not match a tracked person/object")
        ownership[object_id] = athlete
        timestamp = float(value["timestampSeconds"])
        if not math.isfinite(timestamp) or timestamp < times[0] or timestamp > times[-1]+.1:
            raise ValueError("Correction timestamp is outside this video")
        point, box = value.get("point"), value.get("box")
        if point is None and box is None:
            raise ValueError("An object correction requires a point or box")
        if point is not None and (len(point) != 2 or not all(math.isfinite(v) for v in point)
                                  or not 0 <= point[0] < width or not 0 <= point[1] < height):
            raise ValueError("Correction point must use original-image pixel coordinates")
        if box is not None and (len(box) != 4 or not all(math.isfinite(v) for v in box)
                                or not 0 <= box[0] < box[2] <= width or not 0 <= box[1] < box[3] <= height):
            raise ValueError("Correction box must be [x1,y1,x2,y2] in original-image pixels")
        result.setdefault(nearest_index(times, timestamp), []).append(value)
    if len(set(ownership.values())) != len(ownership):
        raise ValueError("Each athlete must have one stable objectId in the corrections file")
    return result


def aligned_frames(video, pose_frames, materialize=None):
    decoder = PrefetchedVideoDecoder(video, decoder=VideoDecoder(video, materialize=materialize))
    count = 0
    try:
        for index, (timestamp, image) in enumerate(decoder):
            if index >= len(pose_frames) or abs(timestamp-pose_frames[index]["timestampSeconds"]) > 1e-7:
                raise ValueError("Pose timestamps do not match the original video")
            count += 1
            yield index, timestamp, image, pose_frames[index]["athletes"]
        if count != len(pose_frames):
            raise ValueError("Pose frame count does not match the original video")
    finally:
        decoder.close()


def detect_candidates(video, frames, models_root, device, progress):
    detector = GroundingDetector(models_root/"grounding_dino", device)
    detections, next_time, targets = {}, -1.0, set()
    for index, frame in enumerate(frames):
        if frame["timestampSeconds"] >= next_time:
            targets.add(index)
            next_time = frame["timestampSeconds"]+POLICY["detectionIntervalSeconds"]
    try:
        for index, timestamp, image, athletes in aligned_frames(video, frames, lambda i,t:i in targets):
            if index in targets:
                candidates = detector.detect(image)
                detections[index] = dict(timestampSeconds=timestamp, candidates=candidates)
                progress(.05+.10*index/len(frames), "Finding barbell candidates")
        apply_temporal_ownership(detections, frames)
        if not any(row["assigned"] for row in detections.values()):
            # A two-second scan can repeatedly sample the same point of a fast
            # lift. Retry moving people at higher temporal/spatial resolution;
            # the crop itself never supplies ownership evidence.
            recovery = recovery_targets(frames)
            for index, timestamp, image, athletes in aligned_frames(video, frames, lambda i,t:i in recovery) if recovery else ():
                if index not in recovery:
                    continue
                candidates = []
                for person in athletes:
                    if person["athleteId"] not in recovery[index]:
                        continue
                    x1, y1, x2, y2 = context_crop(person, image.shape[1], image.shape[0])
                    if x2 <= x1 or y2 <= y1:
                        continue
                    for candidate in detector.detect(image[y1:y2, x1:x2]):
                        box = candidate["box"]
                        mapped = dict(candidate, box=[box[0]+x1, box[1]+y1, box[2]+x1, box[3]+y1])
                        # Overlapping person crops may detect the same object.
                        if not any(mapped["label"] == other["label"] and iou(mapped["box"], other["box"]) > .7 for other in candidates):
                            candidates.append(mapped)
                detections[index] = dict(timestampSeconds=timestamp, candidates=candidates, detectionScope="moving-person-recovery")
                progress(.15+.10*index/len(frames), "Rechecking moving athletes for barbells")
            apply_temporal_ownership(detections, frames)
    finally:
        release_model(detector)
    return detections


def recovery_targets(frames):
    """Bound expensive crop detection to observed wrist/shoulder movement."""
    series = {}
    for index, frame in enumerate(frames):
        for person in frame["athletes"]:
            if person.get("trackingState") != "Tracked":
                continue
            for point in person.get("keypoints", []):
                if point["joint"] in ("LeftWrist", "RightWrist", "LeftShoulder", "RightShoulder") and point["confidence"] >= .4:
                    # Keep each joint separate: switching between a hidden left
                    # hand and visible right hand must not manufacture movement.
                    series.setdefault((person["athleteId"], point["joint"]), []).append(
                        (index, frame["timestampSeconds"], point["y"], person["boundingBox"]["height"]))
    targets = {}
    for (identity, joint), rows in series.items():
        next_time = -1.
        for position, (index, timestamp, y, height) in enumerate(rows):
            if timestamp < next_time:
                continue
            first = position
            while first > 0 and timestamp-rows[first-1][1] <= .5:
                first -= 1
            nearby = rows[first:position+1]
            if len(nearby) < 2 or max(row[2] for row in nearby)-min(row[2] for row in nearby) < max(5., .015*height):
                continue
            targets.setdefault(index, set()).add(identity)
            next_time = timestamp+.5
    # The budget is per person, not per joint; four independently sampled
    # anchors must not multiply inference work by four.
    scheduled, next_by_person = {}, {}
    for index, identities in sorted(targets.items()):
        timestamp = frames[index]["timestampSeconds"]
        for identity in identities:
            if timestamp >= next_by_person.get(identity, -1.):
                scheduled.setdefault(index, set()).add(identity)
                next_by_person[identity] = timestamp+.5
    return scheduled


def apply_temporal_ownership(detections, frames):
    half_window = POLICY["ownershipWindowSeconds"]/2
    times = [frame["timestampSeconds"] for frame in frames]
    # Each scheduled detection rounds to the next decoded frame. Two intervals
    # on either side may drift by two source frames beyond the nominal 4 s.
    tolerance = min(.1, 2*float(np.median(np.diff(times)))) if len(times) > 1 else 0.
    for index, row in detections.items():
        # Preparation and leaving the bench move the hands independently of the
        # bar. Nearby motion can recover ownership when whole-clip proof fails.
        local_detections = {key: value for key, value in detections.items()
                            if abs(value["timestampSeconds"]-row["timestampSeconds"]) <= half_window+tolerance}
        evidence = {}
        for ci, candidate in enumerate(row["candidates"]):
            candidate_evidence = temporal_motion_evidence(candidate, detections, frames,
                POLICY["ownershipMinMotionCorrelation"], POLICY["ownershipMinMotionSamples"])
            scope = "whole-clip"
            # Preserve established ownership even while its owner is absent or
            # temporarily ambiguous. A nearby spotter can briefly mirror a lift;
            # local evidence must not override broader accepted motion proof.
            if not any(value["accepted"] for value in candidate_evidence.values()):
                candidate_evidence = temporal_motion_evidence(candidate, local_detections, frames,
                    POLICY["ownershipMinMotionCorrelation"], POLICY["ownershipLocalMinMotionSamples"])
                scope = "local-window"
            evidence[ci] = {identity: dict(value, scope=scope) for identity, value in candidate_evidence.items()}
        row["ownershipEvidence"] = evidence
        row["assigned"] = assign_candidates(row["candidates"], frames[int(index)]["athletes"],
            POLICY["associationMinScore"], POLICY["associationMinMargin"], evidence)


def mask_box(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) < 12:
        return None
    return [float(xs.min()), float(ys.min()), float(xs.max()+1), float(ys.max()+1)]


def appearance(image, box):
    x1, y1, x2, y2 = map(int, box)
    crop = image[max(0, y1):y2, max(0, x1):x2]
    if not crop.size:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [12, 8], [0, 180, 0, 256])
    return cv2.normalize(histogram, histogram).flatten()


def track_objects(video, frames, detections, corrections, artifact_dir, models_root, device, progress):
    if not corrections and not any(row.get("assigned") for row in detections.values()):
        progress(.75, "No confirmed barbell owner; measurements unavailable")
        return [[] for _ in frames]
    tracker = SamVideoTracker(models_root/"sam2", device)
    states, outputs = {}, []
    manual_athletes = {c["athleteId"] for rows in corrections.values() for c in rows}
    artifact_dir.mkdir(parents=True, exist_ok=True)
    first_prompt = min([int(i) for i,row in detections.items() if row.get("assigned")]+list(corrections), default=len(frames))
    try:
        for index, timestamp, image, athletes in aligned_frames(video, frames, lambda i,t:i>=first_prompt):
            if image is None:
                outputs.append([])
                if index % 30 == 0:
                    progress(.25+.50*index/len(frames), "Preparing object tracking")
                continue
            corrected_points = {}
            assigned = detections.get(index, {}).get("assigned", {})
            for athlete_id, candidate in assigned.items():
                object_id = f"bar-{athlete_id}"
                if athlete_id in manual_athletes:
                    continue
                if object_id not in states:
                    tracker.add(object_id, index, image.shape[:2], box=candidate["box"])
                    states[object_id] = dict(athleteId=athlete_id, lastBox=candidate["box"], lastTime=timestamp,
                        lastAthleteTime=timestamp, appearance=appearance(image, candidate["box"]), point=MeasurementPoint(), lost=False)
                elif states[object_id]["lost"]:
                    state = states[object_id]
                    observed = appearance(image, candidate["box"])
                    similarity = cv2.compareHist(state["appearance"], observed, cv2.HISTCMP_CORREL) if state["appearance"] is not None and observed is not None else -1
                    # Re-detection is not permission to switch plates/bars. Require
                    # same owner, short gap, overlapping geometry and appearance.
                    if timestamp-state["lastTime"] <= 4.0 and iou(state["lastBox"], candidate["box"]) >= .6 and similarity >= .85:
                        tracker.add(object_id, index, image.shape[:2], box=candidate["box"])
                        state["lost"] = False
                        state.pop("rejectionReason", None)
            for correction in corrections.get(index, []):
                object_id = correction["objectId"]
                tracker.add(object_id, index, image.shape[:2], box=correction.get("box"), point=correction.get("point"))
                if object_id not in states:
                    states[object_id] = dict(athleteId=correction["athleteId"], lastBox=correction.get("box"),
                        lastTime=timestamp, lastAthleteTime=timestamp, appearance=None, point=MeasurementPoint(), lost=False)
                states[object_id]["manualTarget"] = True
                states[object_id]["lost"] = False
                states[object_id].pop("rejectionReason", None)
                states[object_id]["lastTime"] = timestamp
                states[object_id]["lastBox"] = correction.get("box")
                if correction.get("point") is not None:
                    corrected_points[object_id] = correction["point"]
            masks = tracker.track(index, image) if states else {}
            rows = []
            for object_id, state in states.items():
                mask, confidence = masks[object_id]
                box = mask_box(mask)
                person = next((a for a in athletes if a["athleteId"] == state["athleteId"]), None)
                valid = box is not None and confidence >= .5
                unstable_proxy = False
                owner_gap_poses = []
                if valid and state["lost"]:
                    observed = appearance(image, box)
                    similarity = cv2.compareHist(state["appearance"], observed, cv2.HISTCMP_CORREL) if state["appearance"] is not None and observed is not None else -1
                    valid = timestamp-state["lastTime"] <= .5 and state["lastBox"] is not None and iou(state["lastBox"], box) >= .6 and similarity >= .85
                    if state.get("rejectionReason") == "sam-mask-covers-athlete-torso":
                        valid = False  # Require a new prompt after semantic identity failure.
                # A user-selected physical object can remain racked before its
                # confirmed owner enters the frame. Pose proximity is evidence for
                # automatic ownership only; mask/point/geometry checks still apply.
                if valid and state.get("manualTarget"):
                    if person is not None and person.get("trackingState") == "Tracked":
                        state["lastAthleteTime"] = timestamp
                        state["lastAthletePose"] = person
                elif valid and person is not None and person.get("trackingState") == "Tracked":
                    # The binding already passed temporal/manual confirmation.
                    # Occluded wrists must not discard a stable SAM object while
                    # its same tracked owner remains nearby. SAM continuity below
                    # still applies and this path never changes athleteId.
                    valid = association_score(dict(box=box, score=confidence), person) >= .35 or confirmed_owner_nearby(box, person)
                    if valid:
                        state["lastAthleteTime"] = timestamp
                        state["lastAthletePose"] = person
                elif valid:
                    last_seen = state.get("lastAthleteTime", state["lastTime"])
                    valid = timestamp-last_seen <= .5
                    if not valid and state.get("lastAthletePose") is not None:
                        # Offline evidence must confirm the SAME identity returns.
                        # Continue measuring observed masks, never synthesize a pose
                        # or reassign a bar to somebody standing in the old location.
                        deadline = last_seen+POLICY["ownerReacquisitionSeconds"]
                        for future_index in range(index+1, len(frames)):
                            future = frames[future_index]
                            if future["timestampSeconds"] > deadline:
                                break
                            returning = next((a for a in future["athletes"]
                                if a["athleteId"] == state["athleteId"] and a.get("trackingState") == "Tracked"), None)
                            if returning is not None:
                                valid = iou(state["lastBox"], box) >= .6 and confirmed_owner_nearby(box, state["lastAthletePose"]) and confirmed_owner_nearby(box, returning)
                                if valid:
                                    owner_gap_poses = [state["lastAthletePose"], returning]
                                break
                if valid and state["lastBox"] is not None:
                    previous = state["lastBox"]
                    distance = math.hypot((box[0]+box[2]-previous[0]-previous[2])/2,
                                          (box[1]+box[3]-previous[1]-previous[3])/2)
                    scale = max(previous[2]-previous[0], previous[3]-previous[1], 20)
                    area_ratio = ((box[2]-box[0])*(box[3]-box[1]))/max(1., (previous[2]-previous[0])*(previous[3]-previous[1]))
                    valid = distance <= .5*scale and .2 <= area_ratio <= 5.
                    unstable_proxy = distance > .15*scale or not .67 <= area_ratio <= 1.5
                measurement = state["point"].update(image, mask, corrected_points.get(object_id), proxy_box=box) if valid else None
                contamination = torso_contamination(mask, person) if valid else None
                if valid and contamination is None:
                    for owner_pose in owner_gap_poses:
                        contamination = torso_contamination(mask, owner_pose)
                        if contamination is not None:
                            break
                if contamination is not None:
                    valid = False
                    state["rejectionReason"] = contamination["reason"]
                if not valid:
                    state["lost"] = True
                    state["point"].update(image, None)
                    rows.append(dict(objectId=object_id, athleteId=state["athleteId"], box=None,
                        maskPath=None, confidence=confidence, trackingState="Lost", measurement=None,
                        rejectionReason=state.get("rejectionReason", "tracking-continuity-not-confirmed")))
                    continue
                state["lastBox"], state["lastTime"] = box, timestamp
                state["lost"] = False
                state.pop("rejectionReason", None)
                if state["appearance"] is None:
                    state["appearance"] = appearance(image, box)
                # Artifact filenames never contain user-controlled object ids.
                mask_path = artifact_dir/f"{index:07d}-{tracker.numeric_ids[object_id]}.png"
                if not cv2.imwrite(str(mask_path), mask.astype(np.uint8)*255):
                    raise OSError(f"Cannot save segmentation mask: {mask_path}")
                if measurement is not None and measurement["isProxy"] and unstable_proxy:
                    measurement["quality"] = "Poor"
                rows.append(dict(objectId=object_id, athleteId=state["athleteId"], box=box_dict(box),
                    maskPath=str(mask_path.resolve()), confidence=confidence, trackingState="Tracked", measurement=measurement,
                    maskValidation=contamination))
            outputs.append(rows)
            if index % 10 == 0:
                progress(.25+.50*index/len(frames), "Tracking objects with SAM 2 video memory")
    finally:
        release_model(tracker)
    return outputs


def classify_exercises(video, frames, detections, models_root, device, progress, object_frames=None):
    times = [f["timestampSeconds"] for f in frames]
    present = {}
    for index, frame in enumerate(frames):
        for person in frame["athletes"]:
            if person.get("trackingState") == "Tracked":
                present.setdefault(person["athleteId"], []).append(index)
    verified_owners = {o["athleteId"] for frame in (object_frames or []) for o in frame if o["trackingState"] == "Tracked"}
    classifier = ExerciseClassifier(models_root/"xclip", device) if verified_owners.intersection(present) else None
    scheduled, windows, predictions = {}, {}, {identity: [] for identity in present}
    for identity, indices in present.items():
        # These tracks would be rejected by the ownership gate regardless of
        # X-CLIP scores. Keep their Unknown result without running the model.
        if identity not in verified_owners:
            continue
        start, end = times[indices[0]], times[indices[-1]]
        while end-start >= .5:
            stop = min(start+POLICY["windowSeconds"], end)
            targets = [nearest_index(times, float(t)) for t in np.linspace(start, stop, classifier.num_frames)]
            key = len(windows)
            windows[key] = dict(athleteId=identity, startSeconds=start, endSeconds=stop, targets=targets, samples={}, actualTimes={})
            for slot, index in enumerate(targets):
                scheduled.setdefault(index, []).append((key, slot))
            start = stop
    try:
        selected_frames = aligned_frames(video, frames, lambda i,t:i in scheduled) if scheduled else ()
        for index, timestamp, image, athletes in selected_frames:
            for key, slot in scheduled.get(index, []):
                window = windows[key]
                person = next((a for a in athletes if a["athleteId"] == window["athleteId"] and a.get("trackingState") == "Tracked"), None)
                if person is not None:
                    # Moving crop follows that person's pose, while preserving gym
                    # context. Every sample remains mapped to its original PTS.
                    object_boxes = [o["box"] for o in (object_frames[index] if object_frames is not None else [])
                                    if o["athleteId"] == window["athleteId"] and o["trackingState"] == "Tracked" and o.get("box")]
                    from .geometry import xyxy
                    x1, y1, x2, y2 = context_crop(person, image.shape[1], image.shape[0], [xyxy(b) for b in object_boxes])
                    crop = image[y1:y2, x1:x2]
                    if crop.size:
                        # Pad to square rather than stretching body geometry; model
                        # processor still owns normalization and target resolution.
                        height, width = crop.shape[:2]
                        side = max(height, width)
                        square = np.zeros((side, side, 3), dtype=np.uint8)
                        square[(side-height)//2:(side-height)//2+height, (side-width)//2:(side-width)//2+width] = crop
                        rgb = cv2.cvtColor(cv2.resize(square, (classifier.image_size, classifier.image_size)), cv2.COLOR_BGR2RGB)
                        window["samples"][slot] = rgb
                        window["actualTimes"][slot] = timestamp
                if index == window["targets"][-1] and slot == classifier.num_frames-1:
                    if len(window["samples"]) == classifier.num_frames:
                        prediction = classifier.classify([window["samples"][i] for i in range(classifier.num_frames)])
                    else:
                        prediction = dict(scores={}, promptLogits=[], decision="Unknown", score=0., margin=0., reason="Person absent in temporal samples")
                    prediction.update(startSeconds=window["startSeconds"], endSeconds=window["endSeconds"],
                                      sampleTimestamps=[window["actualTimes"].get(i) for i in range(classifier.num_frames)])
                    predictions[window["athleteId"]].append(prediction)
                    window["samples"].clear()
            if index % 30 == 0:
                progress(.75+.24*index/len(frames), "Classifying exercise sequences with X-CLIP")
    finally:
        if classifier is not None:
            release_model(classifier)
    result = []
    for identity, rows in predictions.items():
        confident = [row for row in rows if row["decision"] != "Unknown" and row["scores"]]
        label, score, margin = "Unknown", 0., 0.
        if confident:
            average = {label: float(np.mean([row["scores"][label] for row in confident])) for label in confident[0]["scores"]}
            label, score, margin = decide(average)
            if sum(row["decision"] == label for row in confident)/len(confident) < .6:
                label = "Unknown"
        model_label = label
        verified_owner = identity in verified_owners
        if not verified_owner:
            label = "Unknown"
        result.append(dict(athleteId=identity, exercise=label, modelExercise=model_label,
            inferenceStatus="classified" if verified_owner else "skipped-no-verified-object-owner",
            ownershipGate="verified-object-owner" if verified_owner else "no-verified-object-owner",
            score=score, margin=margin, windows=rows,
            method="xclip-window-v1", aggregation="mean logits over accepted windows; >=60% decision agreement; final abstention without verified object ownership",
            scoreMeaning="relative prompt softmax, not calibrated probability"))
    return result
