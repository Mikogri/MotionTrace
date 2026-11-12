"""A measured object may survive a bounded, retrospectively confirmed pose gap."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from vision.pipeline import track_objects


class OwnerContinuityTests(unittest.TestCase):
    def run_gap(self, returning=1, return_time=1.2, jumped=False, contaminated=False, manual=False, distant=False):
        person = dict(athleteId=1, trackingState="Tracked",
                      boundingBox=dict(x=10, y=10, width=80, height=80),
                      keypoints=[dict(joint="LeftWrist", x=40, y=50, confidence=.9)])
        if distant:
            person["boundingBox"]["x"] = 1000
            person["keypoints"][0]["x"] = 1000
        times = [0., .2, .4, .6, .8, 1., return_time]
        frames = [dict(timestampSeconds=t, athletes=[person] if i == 0 and not manual else
                       [dict(person, athleteId=returning)] if i == len(times)-1 else [])
                  for i, t in enumerate(times)]
        image = np.random.default_rng(7).integers(0, 256, (100, 200, 3), dtype=np.uint8)
        mask = np.zeros((100, 200), bool)
        mask[45:55, 20:70] = True
        masks = []
        for i in range(len(times)):
            current = np.roll(mask, 100, axis=1) if jumped and i == 3 else mask.copy()
            if contaminated and i == (len(times)-1 if manual else 3):
                current[50, 30] = False
            masks.append({"bar-1": (current, .95)})
        decoded = [(i, t, image, frames[i]["athletes"]) for i, t in enumerate(times)]
        detections = {0: dict(assigned={1: dict(box=[20, 45, 70, 55])})}
        corrections = {0: [dict(objectId="bar-1", athleteId=1, point=[40, 50], box=[20, 45, 70, 55])]} if manual else {}
        with tempfile.TemporaryDirectory() as directory, \
             patch("vision.pipeline.aligned_frames", return_value=iter(decoded)), \
             patch("vision.pipeline.SamVideoTracker") as tracker, \
             patch("vision.pipeline.torso_contamination", side_effect=lambda m,p:
                   dict(reason="sam-mask-covers-athlete-torso") if p and p.get("trackingState") == "Tracked"
                   and not m[50,30] else None), \
             patch("vision.pipeline.release_model"):
            tracker.return_value.numeric_ids = {"bar-1": 1}
            tracker.return_value.track.side_effect = masks
            return track_objects("unused", frames, detections, corrections, Path(directory), Path("."),
                                 "cpu", lambda *args: None)

    def test_manual_reference_survives_initial_empty_rack_until_owner_arrives(self):
        result = self.run_gap(manual=True, return_time=3.)
        self.assertTrue(all(frame[0]["trackingState"] == "Tracked" for frame in result))
        for frame in result:
            self.assertEqual(1, frame[0]["athleteId"])
            self.assertEqual("manual-lk", frame[0]["measurement"]["source"])
            self.assertAlmostEqual(40, frame[0]["measurement"]["x"], places=2)
            self.assertFalse(frame[0]["measurement"]["isProxy"])

    def test_manual_reference_does_not_depend_on_owner_proximity(self):
        result = self.run_gap(manual=True, distant=True)
        self.assertEqual("Tracked", result[-1][0]["trackingState"])
        self.assertEqual("manual-lk", result[-1][0]["measurement"]["source"])

    def test_manual_reference_still_rejects_owner_torso_mask(self):
        result = self.run_gap(manual=True, contaminated=True)
        self.assertEqual("Lost", result[-1][0]["trackingState"])
        self.assertEqual("sam-mask-covers-athlete-torso", result[-1][0]["rejectionReason"])

    def test_manual_reference_still_rejects_geometry_jump(self):
        result = self.run_gap(manual=True, jumped=True)
        self.assertEqual("Lost", result[3][0]["trackingState"])
        self.assertIsNone(result[3][0]["measurement"])

    def test_same_owner_return_preserves_observed_bar_through_short_pose_gap(self):
        result = self.run_gap()
        self.assertTrue(all(frame[0]["trackingState"] == "Tracked" for frame in result))
        self.assertTrue(all(frame[0]["athleteId"] == 1 for frame in result))
        self.assertTrue(all(not frame[0]["measurement"]["isInterpolated"] for frame in result))

    def test_other_person_or_long_absence_does_not_extend_owner_grace(self):
        for options in (dict(returning=2), dict(return_time=3.)):
            with self.subTest(options=options):
                self.assertEqual("Lost", self.run_gap(**options)[3][0]["trackingState"])

    def test_returning_owner_does_not_override_object_geometry_failure(self):
        self.assertEqual("Lost", self.run_gap(jumped=True)[3][0]["trackingState"])

    def test_pose_gap_still_checks_torso_of_confirmed_owner(self):
        result = self.run_gap(contaminated=True)
        self.assertEqual("Lost", result[3][0]["trackingState"])
        self.assertEqual("sam-mask-covers-athlete-torso", result[3][0]["rejectionReason"])


if __name__ == "__main__":
    unittest.main()
