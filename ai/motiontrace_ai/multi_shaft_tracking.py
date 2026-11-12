"""Track distinct bar shafts; temporal athlete ownership is applied separately."""
from dataclasses import dataclass

import cv2
import numpy as np

from .shaft_tracking import distance, flow


def _copy(segments):
    return [dict(line=list(s['line']), confidence=float(s['confidence'])) for s in segments]


def _compatible(previous, current, height, perpendicular_fraction):
    """Allow detector angle/anchor noise without joining remote collinear bars."""
    for old in previous:
        a = np.array(old['line'], dtype=float).reshape(2, 2)
        direction = a[1] - a[0]
        length = np.linalg.norm(direction)
        if length < 8:
            continue
        direction /= length
        for new in current:
            b = np.array(new['line'], dtype=float).reshape(2, 2)
            vector = b[1] - b[0]
            other_length = np.linalg.norm(vector)
            if other_length < 8 or abs(np.dot(direction, vector)) / other_length < .94:
                continue
            offset = np.mean(b, axis=0) - a[0]
            perpendicular = abs(direction[0] * offset[1] - direction[1] * offset[0])
            projection = (b - a[0]) @ direction
            longitudinal_gap = max(0., float(np.min(projection)) - length, -float(np.max(projection)))
            if perpendicular <= height * perpendicular_fraction and longitudinal_gap <= height * .12:
                return True
    return False


def _groups(detected, height):
    groups = []
    for segment in sorted(detected, key=lambda s: -np.linalg.norm(np.subtract(s['line'][2:], s['line'][:2]))):
        # Require compatibility with every fragment, preventing chains between bars.
        matches = [g for g in groups if all(_compatible([s], [segment], height, .015) for s in g)]
        if len(matches) == 1:
            matches[0].append(segment)
        else:
            groups.append([segment])
    return [_copy(g) for g in groups]


def _gap(previous, current):
    return min(distance(np.mean(np.array(s['line']).reshape(2, 2), axis=0), r['line'])
               for s in current for r in previous)


def _anchor_overlap(previous, current):
    """Observed support along the old shaft, not distance to its nearest fragment."""
    old = max(previous, key=lambda s: np.linalg.norm(np.subtract(s['line'][2:], s['line'][:2])))
    a, b = np.array(old['line'], dtype=float).reshape(2, 2)
    length = np.linalg.norm(b-a)
    if length < 8:
        return 0.
    direction = (b-a)/length
    intervals = sorted((max(0., float(v.min())), min(length, float(v.max())))
        for s in current for v in [(np.array(s['line']).reshape(2, 2)-a) @ direction])
    end = total = 0.
    for low, high in intervals:
        total += max(0., high-max(low, end))
        end = max(end, high)
    return total/length


def _same_axis(groups, height):
    segments = [s for group in groups for s in group]
    line = max(segments, key=lambda s: np.linalg.norm(np.subtract(s['line'][2:], s['line'][:2])))['line']
    a, b = np.array(line, dtype=float).reshape(2, 2)
    axis = (b-a)/max(1., np.linalg.norm(b-a))
    for segment in segments:
        c, d = np.array(segment['line'], dtype=float).reshape(2, 2)
        vector = d-c
        if abs(np.dot(axis, vector))/max(1., np.linalg.norm(vector)) < .985:
            return False
        offset = (c+d)/2-a
        if abs(axis[0]*offset[1]-axis[1]*offset[0]) > height*.006:
            return False
    return True


@dataclass
class _Track:
    track_id: int
    segments: list
    confirmed: float
    visible: bool = True
    missed: bool = False


class MultiShaftTracker:
    VERSION = 'multi-shaft-lk-5'
    DETECTION_INTERVAL = .1
    MAX_LOSS = .15
    IDENTITY_RETENTION = .4

    def __init__(self, detector):
        self.detector = detector
        self.previous = None
        self.time = None
        self.previous_poses = []
        self.last_detection = -float('inf')
        self.tracks = []
        self.next_id = 1

    def update(self, image, timestamp, poses):
        height, width = image.shape[:2]
        scale = 640 / max(height, width)
        gray = cv2.cvtColor(cv2.resize(image, (round(width * scale), round(height * scale))), cv2.COLOR_BGR2GRAY)
        dt = timestamp - self.time if self.time is not None else 0
        continuous = self.previous is not None and self.previous.shape == gray.shape and 0 < dt <= self.MAX_LOSS
        if self.previous is not None and not continuous:
            self.tracks = []
            self.last_detection = -float('inf')

        # Try a fresh detector anchor on the first frame crossing the loss budget.
        # Dropping first would reset IDs merely because expiry falls between ticks.
        recovery_due = continuous and any(
            timestamp - t.confirmed > self.MAX_LOSS + 1e-8 and
            self.time - t.confirmed <= self.MAX_LOSS + 1e-8 for t in self.tracks)
        # Keep geometry briefly for reciprocal detector matching, never as a measurement.
        self.tracks = [t for t in self.tracks if timestamp - t.confirmed <= self.IDENTITY_RETENTION + 1e-8]
        for track in self.tracks:
            if timestamp - track.confirmed > self.MAX_LOSS + 1e-8:
                track.visible = False
        shifts = {}
        camera = None
        if continuous and self.tracks:
            masks = {}
            combined = np.zeros_like(gray)
            for track in self.tracks:
                mask = np.zeros_like(gray)
                if track.visible:
                    for segment in track.segments:
                        x1, y1, x2, y2 = np.round(np.array(segment['line']) * scale).astype(int)
                        cv2.line(mask, (x1, y1), (x2, y2), 255, 7)
                masks[track.track_id] = mask
                combined |= mask
            background = np.full_like(gray, 255)
            for pose in self.previous_poses:
                box = pose['boundingBox']
                x, y = box['x'] * scale, box['y'] * scale
                cv2.rectangle(background, (int(x) - 8, int(y) - 8),
                              (int(x + box['width'] * scale) + 8, int(y + box['height'] * scale) + 8), 0, -1)
            background[cv2.dilate(combined, np.ones((25, 25), np.uint8)) > 0] = 0
            camera = flow(self.previous, gray, background, minimum=8)
            for track in self.tracks:
                shift = flow(self.previous, gray, masks[track.track_id]) if track.visible else None
                if shift is not None and np.linalg.norm(shift) < 640 * .08:
                    for segment in track.segments:
                        segment['line'] = (np.array(segment['line']) + np.tile(shift / scale, 2)).tolist()
                    shifts[track.track_id] = shift
                else:
                    track.visible = False

        if recovery_due or timestamp - self.last_detection >= self.DETECTION_INTERVAL - 1e-8:
            groups = _groups(self.detector.detect(image), height)
            self.last_detection = timestamp
            costs = {}
            for ti, track in enumerate(self.tracks):
                for gi, group in enumerate(groups):
                    if _compatible(track.segments, group, height, .04):
                        costs[ti, gi] = _gap(track.segments, group)

            def unique_best(options):
                options = sorted(options)
                if not options or (len(options) > 1 and options[1][0] - options[0][0] < height * .012):
                    return None
                return options[0][1]

            used = set()
            for ti, track in enumerate(self.tracks):
                options = [(cost, g) for (t, g), cost in costs.items() if t == ti]
                gi = unique_best(options)
                if gi is None and len(options) > 1:
                    # Hands/plates can split one shaft into several detector groups.
                    # Prefer a dominant overlapping anchor, never a tiny nearby end.
                    support = sorted([(_anchor_overlap(track.segments, groups[g]), g)
                                      for _, g in options], reverse=True)
                    if (support[0][0] >= .5 and support[0][0] > 2*support[1][0]
                            and _same_axis([groups[g] for _, g in options], height)):
                        gi = support[0][1]
                reciprocal = unique_best([(cost, t) for (t, g), cost in costs.items() if g == gi]) if gi is not None else None
                if reciprocal == ti:
                    # Reanchoring never supplies a displacement; only preceding LK can.
                    if not track.visible or costs[ti, gi] > height * .01:
                        shifts.pop(track.track_id, None)
                    track.segments = groups[gi]
                    track.confirmed = timestamp
                    track.visible = True
                    track.missed = False
                    used.add(gi)
                else:
                    track.missed = True
                    shifts.pop(track.track_id, None)
                    # Ambiguous candidates must not preserve an apparently measured bar.
                    if any(t == ti for t, g in costs):
                        track.visible = False
            for gi, group in enumerate(groups):
                if gi not in used and not any(g == gi for t, g in costs):
                    self.tracks.append(_Track(self.next_id, group, timestamp))
                    self.next_id += 1

        # Retained identities cannot emit stale shafts or LK displacement over the gap.
        self.previous = gray
        self.time = timestamp
        self.previous_poses = poses
        observations = []
        for track in self.tracks:
            if not track.visible:
                continue
            for segment in track.segments:
                segment['line'] = [float(np.clip(v, 0, width if i % 2 == 0 else height)) for i, v in enumerate(segment['line'])]
            reliable = track.track_id in shifts and camera is not None and not track.missed
            delta = (shifts[track.track_id] - camera) / scale if reliable else np.zeros(2)
            observations.append(dict(
                trackId=track.track_id, athleteId=None,
                segments=[dict(zip(('x1', 'y1', 'x2', 'y2'), s['line'])) for s in track.segments],
                confidence=float(np.mean([s['confidence'] for s in track.segments])),
                motionReliable=bool(reliable), deltaY=float(delta[1]), deltaSeconds=dt if reliable else 0,
                cameraReliable=camera is not None, cameraDeltaY=float(camera[1] / scale) if camera is not None else 0))
        return observations
