import unittest
from unittest.mock import patch

import numpy as np

from motiontrace_ai.multi_shaft_tracking import MultiShaftTracker


def segment(x1, y, x2):
    return dict(line=[x1, y, x2, y], confidence=.9)


class Detector:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.calls = 0

    def detect(self, image):
        self.calls += 1
        return next(self.frames)


class MultiShaftTrackingTests(unittest.TestCase):
    def test_fragmented_bar_keeps_dominant_overlapping_anchor(self):
        line = lambda values: dict(line=values, confidence=.95)
        old = [line([713, 2058, 1351, 2090]), line([1538, 2114, 1666, 2111])]
        fragments = [line([677, 2089, 780, 2100]), line([938, 2111, 1320, 2127]),
                     line([1485, 2146, 1672, 2157])]
        tracker = MultiShaftTracker(Detector([old, fragments]))
        image = np.zeros((3840, 2160, 3), np.uint8)
        first = tracker.update(image, 0, [])
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=np.zeros(2)):
            second = tracker.update(image, .1, [])
        matched = [s for s in second if s['trackId'] == first[0]['trackId']]
        self.assertEqual(len(matched), 1)
        self.assertTrue(any(s['x1'] == 938 for s in matched[0]['segments']))

    def setUp(self):
        self.image = np.zeros((400, 640, 3), np.uint8)

    def test_long_parallel_bar_does_not_win_an_ambiguous_fragment_match(self):
        # The true bar is now only a short fragment; an unseen background bar
        # has greater longitudinal overlap but is equally far on the other side.
        tracker = MultiShaftTracker(Detector([
            [segment(20, 100, 220)],
            [segment(20, 90, 60), segment(20, 110, 220)],
        ]))
        tracker.update(self.image, 0, [])
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=np.zeros(2)):
            self.assertEqual(tracker.update(self.image, .1, []), [])

    def test_distinct_collinear_bars_and_fragments_share_one_detector_call(self):
        bars = [segment(20, 100, 90), segment(100, 100, 180), segment(400, 100, 600)]
        detector = Detector([bars, list(reversed(bars))])
        tracker = MultiShaftTracker(detector)
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=np.zeros(2)):
            first = tracker.update(self.image, 0, [])
            tracker.update(self.image, .03, [])
            second = tracker.update(self.image, .1, [])
        self.assertEqual(detector.calls, 2)
        self.assertEqual(len(first), 2)
        self.assertEqual(sorted(len(t['segments']) for t in first), [1, 2])
        self.assertEqual([t['trackId'] for t in first], [t['trackId'] for t in second])
        self.assertTrue(all(t['athleteId'] is None for t in first))

    def test_camera_compensation_separate_motion_per_bar(self):
        tracker = MultiShaftTracker(Detector([[segment(20, 100, 200), segment(350, 250, 600)]]))
        first = tracker.update(self.image, 0, [])
        with patch('motiontrace_ai.multi_shaft_tracking.flow', side_effect=[np.array([0., 2.]), np.array([0., 5.]), np.array([0., -2.])]):
            second = tracker.update(self.image, .03, [])
        self.assertTrue(all(t['motionReliable'] for t in second))
        # Groups are ordered by length: the right bar is first.
        self.assertEqual([t['deltaY'] for t in second], [3., -4.])
        self.assertTrue(all(t['deltaSeconds'] == .03 for t in second))
        self.assertTrue(all(not t['motionReliable'] for t in first))

    def test_short_loss_reacquires_id_without_measuring_anchor_jump(self):
        bar = [segment(20, 100, 200)]
        tracker = MultiShaftTracker(Detector([bar, [segment(22, 102, 202)]]))
        first = tracker.update(self.image, 0, [])
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=None):
            self.assertEqual(tracker.update(self.image, .03, []), [])
            returned = tracker.update(self.image, .1, [])
        self.assertEqual(returned[0]['trackId'], first[0]['trackId'])
        self.assertFalse(returned[0]['motionReliable'])
        self.assertEqual(returned[0]['deltaY'], 0)

    def test_detector_miss_support_is_bounded(self):
        tracker = MultiShaftTracker(Detector([[segment(20, 100, 200)], [], [], [segment(20, 100, 200)]]))
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=np.zeros(2)):
            first = tracker.update(self.image, 0, [])
            short = tracker.update(self.image, .1, [])
            self.assertEqual(short[0]['trackId'], first[0]['trackId'])
            self.assertFalse(short[0]['motionReliable'])
            self.assertEqual(tracker.update(self.image, .16, []), [])
            self.assertEqual(tracker.update(self.image, .2, []), [])
            new = tracker.update(self.image, .3, [])
        self.assertEqual(new[0]['trackId'], first[0]['trackId'])
        self.assertFalse(new[0]['motionReliable'])

    def test_expiry_between_detector_ticks_attempts_recovery_before_dropping_id(self):
        bar = [segment(20, 100, 200)]
        detector = Detector([bar, [], bar])
        tracker = MultiShaftTracker(detector)
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=np.zeros(2)):
            first = tracker.update(self.image, 0, [])
            tracker.update(self.image, .1, [])
            tracker.update(self.image, .14, [])
            recovered = tracker.update(self.image, .16, [])
        self.assertEqual(detector.calls, 3)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]['trackId'], first[0]['trackId'])

    def test_failed_expiry_recovery_never_emits_stale_bar(self):
        bar = [segment(20, 100, 200)]
        detector = Detector([bar, [], [], bar])
        tracker = MultiShaftTracker(detector)
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=np.zeros(2)):
            first = tracker.update(self.image, 0, [])
            tracker.update(self.image, .1, [])
            self.assertEqual(tracker.update(self.image, .16, []), [])
            self.assertEqual(tracker.update(self.image, .2, []), [])
            self.assertEqual(detector.calls, 3)
            recovered = tracker.update(self.image, .26, [])
        self.assertEqual(recovered[0]['trackId'], first[0]['trackId'])
        self.assertFalse(recovered[0]['motionReliable'])

    def test_lost_identity_expires_without_emitting_unobserved_bar(self):
        bar = [segment(20, 100, 200)]
        tracker = MultiShaftTracker(Detector([bar, [], [], [], [], bar]))
        first = tracker.update(self.image, 0, [])
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=None):
            for time in (.1, .2, .3, .4):
                self.assertEqual(tracker.update(self.image, time, []), [])
            recovered = tracker.update(self.image, .5, [])
        self.assertNotEqual(recovered[0]['trackId'], first[0]['trackId'])
        self.assertFalse(recovered[0]['motionReliable'])

    def test_expired_measurement_cannot_reacquire_ambiguous_bar(self):
        bars = [segment(20, 100, 200), segment(20, 111, 200)]
        tracker = MultiShaftTracker(Detector([bars, [], [], [segment(20, 105.5, 200)]]))
        self.assertEqual(len(tracker.update(self.image, 0, [])), 2)
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=None):
            for time in (.1, .2, .3):
                self.assertEqual(tracker.update(self.image, time, []), [])

    def test_two_tracks_cannot_claim_one_ambiguous_detection(self):
        tracker = MultiShaftTracker(Detector([[segment(20, 100, 200), segment(20, 111, 200)], [segment(20, 105.5, 200)]]))
        first = tracker.update(self.image, 0, [])
        self.assertEqual(len(first), 2)
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=np.zeros(2)):
            self.assertEqual(tracker.update(self.image, .1, []), [])

    def test_detector_anchor_correction_is_not_measured_motion(self):
        tracker = MultiShaftTracker(Detector([[segment(20, 100, 200)], [segment(20, 105, 200)]]))
        first = tracker.update(self.image, 0, [])
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=np.zeros(2)):
            second = tracker.update(self.image, .1, [])
        self.assertEqual(second[0]['trackId'], first[0]['trackId'])
        self.assertEqual(second[0]['segments'][0]['y1'], 105)
        self.assertEqual(second[0]['deltaY'], 0)
        self.assertFalse(second[0]['motionReliable'])

    def test_detector_angle_and_position_jitter_keeps_identity(self):
        # A short exposed shaft can change endpoint angle considerably between detections.
        tilted = dict(line=[70, 106, 150, 134], confidence=.9)
        tracker = MultiShaftTracker(Detector([[segment(20, 110, 200)], [tilted]]))
        first = tracker.update(self.image, 0, [])
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=np.zeros(2)):
            second = tracker.update(self.image, .1, [])
        self.assertEqual(second[0]['trackId'], first[0]['trackId'])
        self.assertFalse(second[0]['motionReliable'])

    def test_grouping_tolerates_fragment_angle_but_bounds_longitudinal_gap(self):
        tilted = dict(line=[30, 96, 110, 120], confidence=.9)
        tracker = MultiShaftTracker(Detector([[segment(20, 108, 90), tilted, segment(400, 108, 600)]]))
        result = tracker.update(self.image, 0, [])
        self.assertEqual(len(result), 2)
        self.assertEqual(sorted(len(s['segments']) for s in result), [1, 2])

    def test_anchor_tolerance_does_not_jump_to_remote_collinear_bar(self):
        tracker = MultiShaftTracker(Detector([[segment(20, 100, 200)], [segment(400, 110, 600)]]))
        first = tracker.update(self.image, 0, [])
        with patch('motiontrace_ai.multi_shaft_tracking.flow', return_value=None):
            second = tracker.update(self.image, .1, [])
        self.assertEqual(len(second), 1)
        self.assertNotEqual(second[0]['trackId'], first[0]['trackId'])

    def test_long_frame_gap_starts_new_identity(self):
        bar = [segment(20, 100, 200)]
        tracker = MultiShaftTracker(Detector([bar, bar]))
        first = tracker.update(self.image, 0, [])
        second = tracker.update(self.image, .3, [])
        self.assertGreater(second[0]['trackId'], first[0]['trackId'])
        self.assertFalse(second[0]['motionReliable'])


if __name__ == '__main__':
    unittest.main()
