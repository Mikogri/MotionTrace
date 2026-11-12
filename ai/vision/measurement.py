"""Reference points only. Velocity and phase calculations remain in C#."""
import cv2
import numpy as np
from .config import POLICY


def torso_contamination(mask, athlete):
    """A bar crossing the shoulders must not become segmentation of the torso.

    Use only four confident, unclipped joints. The central 65% polygon excludes
    shoulder/hip boundaries and is intentionally conservative: at least 75% of
    this interior must be covered before a mask is rejected. This is a semantic
    contamination check, not a tuned bar-axis estimator.
    """
    if athlete is None or athlete.get("trackingState") != "Tracked":
        return None
    names = ("LeftShoulder", "RightShoulder", "RightHip", "LeftHip")
    joints = {p["joint"]: p for p in athlete.get("keypoints", []) if p["confidence"] >= POLICY["torsoGuardJointConfidence"]}
    if any(name not in joints for name in names):
        return None
    polygon = np.asarray([[joints[name]["x"], joints[name]["y"]] for name in names], np.float32)
    if not np.isfinite(polygon).all() or np.any(polygon[:, 0] <= 1) or np.any(polygon[:, 0] >= mask.shape[1]-1) or np.any(polygon[:, 1] <= 1) or np.any(polygon[:, 1] >= mask.shape[0]-1):
        return None
    center = polygon.mean(axis=0)
    polygon = cv2.convexHull(np.rint(center+(polygon-center)*POLICY["torsoGuardInteriorScale"]).astype(np.int32))
    if cv2.contourArea(polygon) < POLICY["torsoGuardMinimumAreaPixels"]:
        return None
    x, y, width, height = cv2.boundingRect(polygon)
    interior = np.zeros((height, width), np.uint8)
    local_polygon = polygon-np.asarray([[[x, y]]], np.int32)
    cv2.fillConvexPoly(interior, local_polygon, 1)
    covered = float(mask[y:y+height, x:x+width][interior != 0].mean())
    if covered < POLICY["torsoGuardCoverageThreshold"]:
        return None
    return dict(reason="sam-mask-covers-athlete-torso", torsoInteriorCoverage=covered)


class MeasurementPoint:
    def __init__(self):
        self.previous = None
        self.point = None
        self.manual = False

    def update(self, image, mask, correction=None, proxy_box=None):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if self.manual or correction is not None else None
        corrected = correction is not None
        if corrected:
            self.point = np.asarray(correction, dtype=np.float32).reshape(1, 1, 2)
            self.manual = True
        elif self.manual and self.point is not None and self.previous is not None:
            following, status, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, self.point, None,
                winSize=(21, 21), maxLevel=3)
            if following is None or not status.item():
                self.point = None
            else:
                backward, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, self.previous, following, None,
                    winSize=(21, 21), maxLevel=3)
                if backward is None or not back_status.item() or np.linalg.norm(backward-self.point) > 1.5:
                    self.point = None
                else:
                    self.point = following
        self.previous = gray
        if mask is None or not mask.any():
            self.point = None
            return None
        if self.manual:
            if self.point is None:
                return None  # Never silently replace a lost physical point with mask centroid.
            x, y = map(float, self.point.ravel())
            ix, iy = int(round(x)), int(round(y))
            if not (0 <= iy < mask.shape[0] and 0 <= ix < mask.shape[1]) or not mask[iy, ix]:
                self.point = None
                return None
            return dict(x=x, y=y, source="manual-lk", quality="Reduced", isProxy=False,
                        isInterpolated=False, isManualCorrection=corrected)
        if proxy_box is None:
            ys, xs = np.nonzero(mask)
            proxy_box = [xs.min(), ys.min(), xs.max()+1, ys.max()+1]
        return dict(x=float((proxy_box[0]+proxy_box[2]-1)/2), y=float((proxy_box[1]+proxy_box[3]-1)/2),
                    source="mask-proxy", quality="Reduced", isProxy=True,
                    isInterpolated=False, isManualCorrection=False)
