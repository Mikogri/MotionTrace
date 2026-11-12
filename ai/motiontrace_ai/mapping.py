"""Explicit COCO-17 to MotionTrace mapping. Reject incompatible model layouts."""
import math

JOINTS = ('Nose', 'LeftEye', 'RightEye', 'LeftEar', 'RightEar', 'LeftShoulder',
          'RightShoulder', 'LeftElbow', 'RightElbow', 'LeftWrist', 'RightWrist',
          'LeftHip', 'RightHip', 'LeftKnee', 'RightKnee', 'LeftAnkle', 'RightAnkle')
DETECTION_THRESHOLD = 0.5


def map_instance(instance):
    points, scores = instance['keypoints'], instance['keypoint_scores']
    if len(points) != len(JOINTS) or len(scores) != len(JOINTS):
        raise ValueError('Expected COCO-17 joints; this model needs a separate MotionTrace mapper')
    box = instance['bbox']
    if len(box) == 1:
        box = box[0]
    confidence = float(instance['bbox_score'])
    if len(box) != 4 or not all(math.isfinite(float(v)) for v in box) or not math.isfinite(confidence):
        return None
    if confidence < DETECTION_THRESHOLD or box[2] <= box[0] or box[3] <= box[1]:
        return None
    keypoints = []
    for joint, point, score in zip(JOINTS, points, scores):
        x, y, score = float(point[0]), float(point[1]), float(score)
        if not all(math.isfinite(v) for v in (x, y, score)):
            x, y, score = 0.0, 0.0, 0.0
        keypoints.append(dict(joint=joint, x=x, y=y, confidence=max(0, min(1, score))))
    return dict(box=[float(v) for v in box], confidence=max(0, min(1, confidence)), keypoints=keypoints)
