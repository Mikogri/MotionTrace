import unittest
from motiontrace_ai.tracking import AthleteTracker
from motiontrace_ai.mapping import map_instance, JOINTS


def pose(x, y=0):
    return dict(box=[x, y, x+100, y+200], confidence=0.9,
                keypoints=[dict(joint=j, x=x+20, y=y+30, confidence=0.8) for j in JOINTS])


class TrackingTests(unittest.TestCase):
    def test_detection_order_does_not_change_identity(self):
        tracker = AthleteTracker()
        first = tracker.update([pose(0), pose(300)], 0)
        second = tracker.update([pose(302), pose(2)], 0.03)
        # Result ordering is not identity: compare the returned locations instead.
        ids_by_x = {p['boundingBox']['x']: p['athleteId'] for p in second}
        self.assertEqual(first[0]['athleteId'], ids_by_x[2])
        self.assertEqual(first[1]['athleteId'], ids_by_x[302])

    def test_short_occlusion_preserves_identity(self):
        tracker = AthleteTracker()
        first = tracker.update([pose(0)], 0)
        tracker.update([], 0.1)
        self.assertEqual(first[0]['athleteId'], tracker.update([pose(3)], 0.3)[0]['athleteId'])

    def test_long_occlusion_creates_new_track(self):
        tracker = AthleteTracker()
        first = tracker.update([pose(0)], 0)
        self.assertNotEqual(first[0]['athleteId'], tracker.update([pose(0)], 1)[0]['athleteId'])

    def test_single_detection_is_not_confirmed(self):
        tracker = AthleteTracker()
        tracker.update([pose(0)], 0)
        self.assertFalse(tracker.confirmed)
        tracker.update([pose(1)], 0.03)
        tracker.update([pose(2)], 0.06)
        self.assertEqual({1}, tracker.confirmed)

    def test_assignment_is_one_to_one(self):
        tracker = AthleteTracker()
        tracker.update([pose(0)], 0)
        result = tracker.update([pose(2), pose(4)], 0.03)
        self.assertEqual(2, len(set(p['athleteId'] for p in result)))

    def test_mapper_preserves_semantic_joint_and_score(self):
        result = map_instance(dict(keypoints=[[10, 20]]*17, keypoint_scores=[0.7]*17, bbox=[[0, 0, 100, 200]], bbox_score=0.9))
        self.assertEqual('LeftKnee', result['keypoints'][13]['joint'])
        self.assertEqual(0.7, result['keypoints'][13]['confidence'])

    def test_mapper_rejects_incompatible_joint_layout(self):
        with self.assertRaises(ValueError):
            map_instance(dict(keypoints=[], keypoint_scores=[]))


if __name__ == '__main__':
    unittest.main()
