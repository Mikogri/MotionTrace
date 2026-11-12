"""One-to-one temporal association using predicted boxes and confident pose points.

This is short-gap tracking, not appearance re-identification. A long absence creates
a new identity rather than silently guessing that an athlete has returned.
"""
from dataclasses import dataclass
import math


def overlap(a, b):
    x = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    y = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = x * y
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0


@dataclass
class Track:
    identity: int
    pose: dict
    timestamp: float
    velocity: tuple = (0.0, 0.0)
    hits: int = 1


class AthleteTracker:
    MAX_GAP_SECONDS = 0.6
    MIN_HITS = 3
    MAX_COST = 0.85

    def __init__(self):
        self.active = []
        self.next_id = 1
        self.confirmed = set()

    @staticmethod
    def cost(track, pose, timestamp):
        old = track.pose['box']
        dt = timestamp - track.timestamp
        dx, dy = (v * dt for v in track.velocity)
        predicted = [old[0] + dx, old[1] + dy, old[2] + dx, old[3] + dy]
        box = pose['box']
        diagonal = max(1, math.hypot(old[2] - old[0], old[3] - old[1]))
        distance = math.hypot((predicted[0] + predicted[2] - box[0] - box[2]) / 2,
                              (predicted[1] + predicted[3] - box[1] - box[3]) / 2) / diagonal
        iou = overlap(predicted, box)
        if distance > 0.6 or (iou < 0.05 and distance > 0.25):
            return 1e6
        differences = [math.hypot(a['x'] + dx - b['x'], a['y'] + dy - b['y']) / diagonal
                       for a, b in zip(track.pose['keypoints'], pose['keypoints'])
                       if min(a['confidence'], b['confidence']) >= 0.4]
        pose_distance = sum(differences) / len(differences) if differences else distance
        return 0.55 * (1 - iou) + 0.25 * distance + 0.2 * min(pose_distance, 1)

    def update(self, poses, timestamp):
        from scipy.optimize import linear_sum_assignment
        self.active = [t for t in self.active if timestamp - t.timestamp <= self.MAX_GAP_SECONDS]
        assigned = {}
        if self.active and poses:
            costs = [[self.cost(t, p, timestamp) for p in poses] for t in self.active]
            rows, cols = linear_sum_assignment(costs)
            for row, col in zip(rows, cols):
                if costs[row][col] > self.MAX_COST:
                    continue
                track = self.active[row]
                old, new = track.pose['box'], poses[col]['box']
                dt = timestamp - track.timestamp
                if dt <= 0:
                    raise ValueError('Tracker timestamps must increase')
                measured = ((new[0] + new[2] - old[0] - old[2]) / (2 * dt),
                            (new[1] + new[3] - old[1] - old[3]) / (2 * dt))
                track.velocity = tuple(0.5 * a + 0.5 * b for a, b in zip(track.velocity, measured))
                track.pose, track.timestamp = poses[col], timestamp
                track.hits += 1
                assigned[col] = track
        for i, pose in enumerate(poses):
            if i not in assigned:
                track = Track(self.next_id, pose, timestamp)
                self.next_id += 1
                self.active.append(track)
                assigned[i] = track
        result = []
        for i, track in assigned.items():
            if track.hits >= self.MIN_HITS:
                self.confirmed.add(track.identity)
            pose = poses[i]
            x1, y1, x2, y2 = pose['box']
            result.append(dict(athleteId=track.identity, boundingBox=dict(x=x1, y=y1, width=x2-x1, height=y2-y1),
                               confidence=pose['confidence'], keypoints=pose['keypoints']))
        return result
