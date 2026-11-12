"""Optimizations preserve the frames and measurements consumed by the models."""
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

from vision.measurement import MeasurementPoint
from vision.pipeline import classify_exercises, detect_candidates


class PerformanceContractTests(unittest.TestCase):
    def test_detection_keeps_original_timestamp_schedule(self):
        frames = [dict(timestampSeconds=i*.501, athletes=[]) for i in range(11)]
        used = []

        def decoded(video, poses, materialize):
            for i, frame in enumerate(poses):
                image = np.full((4, 4, 3), i, np.uint8) if materialize(i, frame['timestampSeconds']) else None
                yield i, frame['timestampSeconds'], image, []

        with patch('vision.pipeline.aligned_frames', side_effect=decoded), \
             patch('vision.pipeline.GroundingDetector') as detector, \
             patch('vision.pipeline.release_model'):
            detector.return_value.detect.side_effect = lambda image: used.append(int(image[0, 0, 0])) or []
            actual = detect_candidates('unused', frames, Path('.'), 'cpu', lambda *args: None)
        self.assertEqual([0, 4, 8], used)
        self.assertEqual([0, 4, 8], list(actual))

    def test_unconfirmed_people_do_not_load_or_run_classifier(self):
        frames = [dict(timestampSeconds=i*.5, athletes=[dict(athleteId=1, trackingState='Tracked')]) for i in range(10)]
        with patch('vision.pipeline.ExerciseClassifier') as model, patch('vision.pipeline.aligned_frames') as decode:
            result = classify_exercises('unused', frames, {}, Path('.'), 'cpu', lambda *args: None, [[] for _ in frames])
        model.assert_not_called()
        decode.assert_not_called()
        self.assertEqual('Unknown', result[0]['exercise'])
        self.assertEqual('no-verified-object-owner', result[0]['ownershipGate'])

    def test_reused_mask_box_has_identical_proxy_measurement(self):
        mask = np.zeros((80, 100), bool)
        mask[20:39, 16:73] = True
        image = np.zeros((80, 100, 3), np.uint8)
        expected = MeasurementPoint().update(image, mask)
        with patch('vision.measurement.cv2.cvtColor') as gray:
            actual = MeasurementPoint().update(image, mask, proxy_box=[16, 20, 73, 39])
        gray.assert_not_called()
        self.assertEqual(expected, actual)


if __name__ == '__main__':
    unittest.main()
