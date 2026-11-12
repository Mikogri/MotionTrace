"""Association geometry in the rotated original-video coordinate system."""
import math
import numpy as np


def xyxy(box):
    if isinstance(box, dict):
        return [box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"]]
    return list(box)


def box_dict(box):
    return dict(x=float(box[0]), y=float(box[1]), width=float(box[2]-box[0]), height=float(box[3]-box[1]))


def iou(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection / union if union > 0 else 0.0


def association_score(candidate, athlete):
    if athlete.get("trackingState") != "Tracked":
        return 0.0
    body = xyxy(athlete["boundingBox"])
    scale = max(1.0, body[3]-body[1])
    box = candidate["box"]
    # Hands hold the bar in bench/deadlift; shoulders support it in squat.
    anchors = [p for p in athlete.get("keypoints", [])
               if p["joint"] in ("LeftWrist", "RightWrist", "LeftShoulder", "RightShoulder") and p["confidence"] >= .4]
    if not anchors:
        return 0.0
    distances = [math.hypot(max(box[0]-p["x"], 0, p["x"]-box[2]),
                            max(box[1]-p["y"], 0, p["y"]-box[3])) / scale for p in anchors]
    proximity = max(0.0, 1.0-min(distances)/.25)
    cx = (box[0]+box[2])/2
    horizontal = max(0.0, 1.0-abs(cx-(body[0]+body[2])/2)/scale)
    return .75*proximity + .15*horizontal + .10*float(candidate["score"])


def assign_candidates(candidates, athletes, minimum=.50, margin=.12, motion_scores=None):
    """Conservative one-object/one-person assignment; ties request manual input."""
    edges = []
    for ci, candidate in enumerate(candidates):
        ranking = []
        for athlete in athletes:
            score = association_score(candidate, athlete)
            if motion_scores is not None:
                motion = motion_scores.get(ci, {}).get(athlete["athleteId"], {})
                if not motion.get("accepted", False):
                    continue
                score = .4*score+.6*motion["correlation"] if score >= minimum else 0.
            ranking.append((score, athlete["athleteId"]))
        ranking.sort(reverse=True)
        if not ranking or ranking[0][0] < minimum:
            continue
        if len(ranking) > 1 and ranking[0][0]-ranking[1][0] < margin:
            continue
        edges.append((ranking[0][0], ci, ranking[0][1]))
    # Do not select arbitrarily between two equally plausible objects for one person.
    result = {}
    for athlete in athletes:
        choices = sorted([e for e in edges if e[2] == athlete["athleteId"]], reverse=True)
        if not choices:
            continue
        # DINO often returns a plate inside a whole-bar detection. Prefer the whole
        # bar only after ownership was established, not by global detector score.
        bars = [e for e in choices if "barbell" in candidates[e[1]]["label"]]
        if bars:
            choices = bars
        if len(choices) > 1 and choices[0][0]-choices[1][0] < margin:
            continue
        result[athlete["athleteId"]] = candidates[choices[0][1]]
    return result


def temporal_motion_evidence(candidate, detections, frames, minimum_correlation=.65, minimum_samples=3):
    """Geometry alone cannot distinguish a spotter standing behind a bench.

    Compare a candidate's temporal vertical displacement with each person's
    reliable wrists (and shoulders for squat). This is a conservative ownership
    gate, not an exercise/phase classifier. Insufficient motion abstains.
    """
    series = {}
    for index, row in detections.items():
        def affinity(box):
            reference = candidate["box"]
            horizontal_intersection = max(0., min(reference[2], box[2])-max(reference[0], box[0]))
            horizontal_union = max(reference[2], box[2])-min(reference[0], box[0])
            horizontal = horizontal_intersection/max(1., horizontal_union)
            distance = abs((reference[1]+reference[3]-box[1]-box[3])/2)
            # A deadlift can move farther vertically than the bar's box height.
            # Require the same horizontal extent rather than overlapping masks.
            scale = max(reference[2]-reference[0], reference[3]-reference[1])
            return .7*horizontal+.3*max(0., 1.-distance/max(1., .6*scale))
        matches = sorted([(affinity(c["box"]), c) for c in row["candidates"]
                          if c["label"] == candidate["label"]], key=lambda pair: pair[0], reverse=True)
        if not matches or matches[0][0] < .65:
            continue
        if len(matches) > 1 and matches[0][0]-matches[1][0] < .15:
            continue
        box = matches[0][1]["box"]
        bar_y = (box[1]+box[3])/2
        for athlete in frames[int(index)]["athletes"]:
            if athlete.get("trackingState") != "Tracked":
                continue
            for group, names in (("wrists", ("LeftWrist", "RightWrist")), ("shoulders", ("LeftShoulder", "RightShoulder"))):
                points = [p for p in athlete.get("keypoints", []) if p["joint"] in names and p["confidence"] >= .3]
                if not points:
                    continue
                # Do not let an unrelated walking person elsewhere explain a bar.
                if association_score(matches[0][1], athlete) < .35:
                    continue
                key = (athlete["athleteId"], group)
                series.setdefault(key, []).append((bar_y, float(np.median([p["y"] for p in points])), athlete["boundingBox"]["height"]))
    evidence = {}
    for (identity, group), rows in series.items():
        if len(rows) < minimum_samples:
            continue
        bar, body, scales = np.asarray(rows).T
        minimum_excursion = max(5., .015*float(np.median(scales)))
        bar_range, body_range = float(np.ptp(bar)), float(np.ptp(body))
        if bar_range < minimum_excursion or body_range < minimum_excursion:
            continue
        correlation = float(np.corrcoef(bar, body)[0, 1])
        amplitude_ratio = float(np.std(body)/max(np.std(bar), 1e-6))
        accepted = math.isfinite(correlation) and correlation >= minimum_correlation and .15 <= amplitude_ratio <= 4.
        row = dict(accepted=accepted, correlation=correlation if math.isfinite(correlation) else 0.,
                   samples=len(rows), bodyPoints=group, bodyToObjectMotionRatio=amplitude_ratio,
                   objectExcursionPixels=bar_range, bodyExcursionPixels=body_range)
        # A perfectly correlated but implausibly large shoulder excursion must
        # not erase a valid wrist match (or vice versa).
        rank = (row["accepted"], row["correlation"])
        if identity not in evidence or rank > (evidence[identity]["accepted"], evidence[identity]["correlation"]):
            evidence[identity] = row
    return evidence


def context_crop(athlete, width, height, candidate_boxes=()):
    x1, y1, x2, y2 = xyxy(athlete["boundingBox"])
    for box in candidate_boxes:
        x1, y1, x2, y2 = min(x1, box[0]), min(y1, box[1]), max(x2, box[2]), max(y2, box[3])
    margin = max(x2-x1, y2-y1)*.25
    return [max(0, int(x1-margin)), max(0, int(y1-margin)), min(width, int(math.ceil(x2+margin))), min(height, int(math.ceil(y2+margin)))]


def confirmed_owner_nearby(box, athlete):
    """Continuity fallback only after temporal/manual ownership is established."""
    if athlete.get("trackingState") != "Tracked":
        return False
    body = xyxy(athlete["boundingBox"])
    margin = .2*max(body[2]-body[0], body[3]-body[1])
    return min(box[2], body[2]+margin) > max(box[0], body[0]-margin) and min(box[3], body[3]+margin) > max(box[1], body[1]-margin)
