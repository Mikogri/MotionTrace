"""Focused policy/geometry tests; these are not actual-model accuracy tests."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from vision.geometry import assign_candidates, context_crop, iou, temporal_motion_evidence, confirmed_owner_nearby
from vision.measurement import MeasurementPoint, torso_contamination
from vision.models import decide, SamVideoTracker
from vision.pipeline import apply_temporal_ownership, file_hash, load_corrections, nearest_index, verify_manifest


def athlete(identity, x):
    return dict(athleteId=identity, trackingState="Tracked", boundingBox=dict(x=x, y=10, width=60, height=200),
                keypoints=[dict(joint="LeftWrist", x=x+15, y=100, confidence=.9),
                           dict(joint="RightWrist", x=x+45, y=100, confidence=.9)])


class VisionPolicyTests(unittest.TestCase):
    def test_assignment_uses_geometry_not_global_detector_score(self):
        candidates = [dict(box=[5, 95, 65, 105], score=.6, label="barbell"),
                      dict(box=[300, 95, 400, 105], score=.99, label="barbell")]
        result = assign_candidates(candidates, [athlete(1, 0)])
        self.assertEqual(candidates[0], result[1])

    def test_ambiguous_people_abstain(self):
        self.assertEqual({}, assign_candidates([dict(box=[5, 95, 65, 105], score=.9, label="barbell")],
                                              [athlete(1, 0), athlete(2, 0)]))

    def test_two_people_receive_distinct_bars(self):
        candidates = [dict(box=[5, 95, 65, 105], score=.9, label="barbell"),
                      dict(box=[305, 95, 365, 105], score=.9, label="barbell")]
        self.assertEqual({1: candidates[0], 2: candidates[1]}, assign_candidates(candidates, [athlete(1, 0), athlete(2, 300)]))

    def test_temporal_ownership_rejects_stationary_helper(self):
        frames, detections = [], {}
        for index, y in enumerate([100., 130., 160., 110.]):
            lifter, helper = athlete(2, 0), athlete(1, 0)
            for point in lifter["keypoints"]:
                point["y"] = y
            candidate = dict(box=[0., y-30., 200., y+30.], score=.9, label="barbell")
            frames.append(dict(athletes=[helper, lifter]))
            detections[index] = dict(candidates=[candidate])
        candidate = detections[0]["candidates"][0]
        evidence = temporal_motion_evidence(candidate, detections, frames)
        self.assertNotIn(1, evidence)  # zero excursion is not ownership evidence
        self.assertTrue(evidence[2]["accepted"])
        self.assertEqual({2: candidate}, assign_candidates([candidate], frames[0]["athletes"], motion_scores={0: evidence}))

    def test_motion_gate_does_not_assign_from_two_frames(self):
        detections = {0: dict(candidates=[dict(box=[0., 70., 200., 130.], score=.9, label="barbell")])}
        candidate = detections[0]["candidates"][0]
        evidence = temporal_motion_evidence(candidate, detections, [dict(athletes=[athlete(1, 0)])])
        self.assertEqual({}, assign_candidates([candidate], [athlete(1, 0)], motion_scores={0: evidence}))

    def test_local_ownership_ignores_preparation_and_exit_motion(self):
        frames, detections = [], {}
        for index in range(17):
            y = [100., 120., 150., 125., 100.][index-6] if 6 <= index <= 10 else 100.
            lifter, helper = athlete(2, 0), athlete(1, 0)
            for point in lifter["keypoints"]:
                point["y"] = y if 6 <= index <= 10 else (70. if index % 2 else 165.)
            timestamp = index*2.0001  # real PTS seldom lands on exact seconds
            frames.append(dict(timestampSeconds=timestamp, athletes=[helper, lifter]))
            detections[index] = dict(timestampSeconds=timestamp,
                candidates=[dict(box=[0., y-60., 200., y+60.], score=.9, label="barbell")])
        candidate = detections[8]["candidates"][0]
        global_evidence = temporal_motion_evidence(candidate, detections, frames, minimum_samples=4)
        self.assertFalse(global_evidence.get(2, {}).get("accepted", False))
        apply_temporal_ownership(detections, frames)
        self.assertEqual({2: candidate}, detections[8]["assigned"])
        self.assertEqual(5, detections[8]["ownershipEvidence"][0][2]["samples"])
        self.assertEqual({}, detections[0]["assigned"])
        self.assertEqual({}, detections[16]["assigned"])
        self.assertTrue(all(1 not in row["assigned"] for row in detections.values()))

    def test_local_ownership_keeps_ambiguous_moving_people_unassigned(self):
        frames, detections = [], {}
        for index, y in enumerate([100., 130., 150., 120., 100.]):
            people = [athlete(1, 0), athlete(2, 0)]
            for person in people:
                for point in person["keypoints"]:
                    point["y"] = y
            timestamp = index*2.
            frames.append(dict(timestampSeconds=timestamp, athletes=people))
            detections[index] = dict(timestampSeconds=timestamp,
                candidates=[dict(box=[0., y-30., 200., y+30.], score=.9, label="barbell")])
        apply_temporal_ownership(detections, frames)
        self.assertTrue(all(not row["assigned"] for row in detections.values()))

    def test_global_owner_absence_does_not_allow_local_helper_takeover(self):
        frames, detections = [], {}
        for index, y in enumerate([100., 150., 100., 130., 160., 110., 140., 100., 150., 100., 150.]):
            lifter, helper = athlete(2, 0), athlete(1, 0)
            for point in lifter["keypoints"]:
                point["y"] = y
            if index == 5:
                lifter["trackingState"] = "Lost"
            for point in helper["keypoints"]:
                point["y"] = y if 3 <= index <= 7 else 250.-y
            timestamp = index*2.
            frames.append(dict(timestampSeconds=timestamp, athletes=[lifter, helper]))
            detections[index] = dict(timestampSeconds=timestamp,
                candidates=[dict(box=[0., y-60., 200., y+60.], score=.9, label="barbell")])
        nearby = {index: row for index, row in detections.items() if 3 <= index <= 7}
        local_evidence = temporal_motion_evidence(detections[5]["candidates"][0], nearby, frames, minimum_samples=4)
        self.assertTrue(local_evidence[1]["accepted"])
        apply_temporal_ownership(detections, frames)
        self.assertEqual({}, detections[5]["assigned"])
        self.assertEqual("whole-clip", detections[5]["ownershipEvidence"][0][2]["scope"])
        self.assertTrue(all(1 not in row["assigned"] for row in detections.values()))

    def test_global_three_sample_proof_preserves_initial_assignment(self):
        frames, detections = [], {}
        for index in range(9):
            y = 100.+index*5.
            person = athlete(1, 0)
            for point in person["keypoints"]:
                point["y"] = y
            if index not in (0, 4, 8):
                person["trackingState"] = "Lost"
            timestamp = index*2.
            frames.append(dict(timestampSeconds=timestamp, athletes=[person]))
            detections[index] = dict(timestampSeconds=timestamp,
                candidates=[dict(box=[0., y-30., 200., y+30.], score=.9, label="barbell")])
        apply_temporal_ownership(detections, frames)
        self.assertEqual({1}, set(detections[0]["assigned"]))
        self.assertEqual("whole-clip", detections[0]["ownershipEvidence"][0][1]["scope"])

    def test_rejected_high_correlation_does_not_override_valid_joint_group(self):
        frames, detections = [], {}
        for index, (bar_y, wrist_y) in enumerate(zip([100., 110., 120., 115., 100.], [100., 111., 119., 114., 101.])):
            person = athlete(1, 0)
            for point in person["keypoints"]:
                point["y"] = wrist_y
            person["keypoints"].append(dict(joint="LeftShoulder", x=30., y=200.+5*(bar_y-100), confidence=.9))
            frames.append(dict(athletes=[person]))
            detections[index] = dict(candidates=[dict(box=[0., bar_y-30., 200., bar_y+30.], score=.9, label="barbell")])
        evidence = temporal_motion_evidence(detections[0]["candidates"][0], detections, frames, minimum_samples=4)
        self.assertTrue(evidence[1]["accepted"])
        self.assertEqual("wrists", evidence[1]["bodyPoints"])

    def test_crop_follows_person_and_clips_original_dimensions(self):
        first = context_crop(athlete(1, 0), 500, 300)
        second = context_crop(athlete(1, 200), 500, 300)
        self.assertEqual(0, first[0])
        self.assertGreater(second[0], first[0])
        self.assertLessEqual(second[2], 500)

    def test_confirmed_owner_context_does_not_accept_lost_or_distant_person(self):
        person = athlete(1, 0)
        person["keypoints"] = []
        self.assertTrue(confirmed_owner_nearby([0, 90, 200, 110], person))
        self.assertFalse(confirmed_owner_nearby([500, 90, 700, 110], person))
        person["trackingState"] = "Lost"
        self.assertFalse(confirmed_owner_nearby([0, 90, 200, 110], person))

    def test_uncertain_classifier_is_unknown(self):
        decision, _, _ = decide(dict(Squat=1., BenchPress=1., Deadlift=1., Snatch=1., CleanAndJerk=1., Unknown=1.))
        self.assertEqual("Unknown", decision)

    def test_explicit_unknown_prompt_can_win(self):
        self.assertEqual("Unknown", decide(dict(Squat=0., BenchPress=0., Deadlift=0., Snatch=0., CleanAndJerk=0., Unknown=10.))[0])

    def test_time_sampling_uses_real_pts(self):
        times = [0., .033, .100, .133, .25]
        self.assertEqual(2, nearest_index(times, .09))
        self.assertEqual(4, nearest_index(times, .8))

    def test_proxy_is_marked_and_missing_mask_returns_null(self):
        point = MeasurementPoint()
        image = np.zeros((40, 60, 3), np.uint8)
        mask = np.zeros((40, 60), bool)
        mask[10:20, 20:40] = True
        value = point.update(image, mask)
        self.assertTrue(value["isProxy"])
        self.assertEqual("mask-proxy", value["source"])
        self.assertIsNone(point.update(image, None))

    def test_manual_point_never_silently_becomes_proxy(self):
        point = MeasurementPoint()
        image = np.zeros((40, 60, 3), np.uint8)
        mask = np.ones((40, 60), bool)
        initial = point.update(image, mask, [20., 10.])
        self.assertFalse(initial["isProxy"])
        self.assertTrue(initial["isManualCorrection"])
        self.assertIsNone(point.update(image, None))
        self.assertIsNone(point.update(image, mask))

    def test_torso_guard_allows_crossing_bar_and_rejects_body_segmentation(self):
        person = dict(trackingState="Tracked", keypoints=[dict(joint=name, x=x, y=y, confidence=.9)
            for name, x, y in [("LeftShoulder", 40, 30), ("RightShoulder", 100, 30), ("LeftHip", 45, 130), ("RightHip", 95, 130)]])
        bar = np.zeros((180, 180), bool)
        bar[60:67, 10:150] = True
        self.assertIsNone(torso_contamination(bar, person))
        torso = np.zeros_like(bar)
        torso[30:131, 40:101] = True
        rejection = torso_contamination(torso, person)
        self.assertEqual("sam-mask-covers-athlete-torso", rejection["reason"])
        person["keypoints"][0]["confidence"] = .2
        self.assertIsNone(torso_contamination(torso, person))

    def test_correction_is_bound_to_video_and_valid_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"correction.json"
            row = dict(objectId="bar-1", athleteId=1, timestampSeconds=1., point=[20., 10.])
            path.write_text(json.dumps(dict(videoHash="a", objects=[row])))
            with self.assertRaisesRegex(ValueError, "different video"):
                load_corrections(path, "b", [0., 1., 2.], 100, 100, {1})
            self.assertEqual(row, load_corrections(path, "a", [0., 1., 2.], 100, 100, {1})[1][0])

    def test_temporal_memory_is_bounded_and_keeps_anchors(self):
        from types import SimpleNamespace
        tracker = SamVideoTracker.__new__(SamVideoTracker)
        tracker.memory_frames = 18
        tracker.session = SimpleNamespace(processed_frames={i: None for i in range(100)},
            output_dict_per_obj={0: dict(cond_frame_outputs={0: {}, 30: {}, 80: {}}, non_cond_frame_outputs={i: {} for i in range(100)})},
            frames_tracked_per_obj={0: {i: {} for i in range(100)}},
            point_inputs_per_obj={0: {0: {}, 30: {}, 80: {}}}, mask_inputs_per_obj={0: {}})
        tracker.prune(99)
        self.assertEqual({99: None}, tracker.session.processed_frames)
        self.assertEqual({0, 80}, set(tracker.session.output_dict_per_obj[0]["cond_frame_outputs"]))
        self.assertEqual(19, len(tracker.session.output_dict_per_obj[0]["non_cond_frame_outputs"]))

    def test_model_integrity_rejects_missing_and_modified_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = dict(models={})
            for name in ("xclip", "grounding_dino", "sam2"):
                (root/name).mkdir()
                path = root/name/"weights.bin"
                path.write_bytes(b"test checkpoint")
                manifest["models"][name] = dict(revision="pinned", files=[dict(path="weights.bin", size=path.stat().st_size, sha256=file_hash(path))])
            verify_manifest(root, manifest)
            (root/"sam2"/"weights.bin").write_bytes(b"othercheckpoints")
            with self.assertRaisesRegex(ValueError, "Corrupted"):
                verify_manifest(root, manifest)
            (root/"sam2"/"weights.bin").unlink()
            with self.assertRaisesRegex(FileNotFoundError, "Missing local"):
                verify_manifest(root, manifest)


if __name__ == "__main__":
    unittest.main()
