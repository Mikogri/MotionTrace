"""Coarse detection must recover fast movement without inventing ownership."""
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from vision.pipeline import detect_candidates, track_objects, recovery_targets


def frames(moving=True):
    result = []
    for i in range(25):
        y = 110 + (30 if i % 4 in (1, 2) and moving else 0)
        person = dict(athleteId=1, trackingState='Tracked',
                      boundingBox=dict(x=100, y=80, width=100, height=200),
                      keypoints=[dict(joint='LeftWrist', x=150, y=y, confidence=.9)])
        result.append(dict(timestampSeconds=i*.5, athletes=[person]))
    return result


class DetectionRecoveryTests(unittest.TestCase):
    def detect(self, poses, moving=True):
        calls = []
        def decode(video, source, materialize):
            for i, frame in enumerate(source):
                image = np.full((500, 600, 3), i, np.uint8) if materialize(i, frame['timestampSeconds']) else None
                yield i, frame['timestampSeconds'], image, frame['athletes']
        def infer(image):
            i = int(image[0,0,0]); calls.append(image.shape)
            # Coarse full-frame scan aliases the 2-second movement cycle.
            y = poses[i]['athletes'][0]['keypoints'][0]['y'] if moving else 110
            if image.shape[:2] == (500,600):
                return [dict(box=[100,100,200,120],score=.9,label='a barbell')]
            # context_crop starts at (50,30).
            return [dict(box=[50,y-35,150,y-25],score=.9,label='a barbell')]
        with patch('vision.pipeline.aligned_frames',side_effect=decode), \
             patch('vision.pipeline.GroundingDetector') as detector, \
             patch('vision.pipeline.release_model'):
            detector.return_value.detect.side_effect = infer
            result=detect_candidates('unused',poses,Path('.'),'cpu',lambda *args:None)
        return result,calls

    def test_dense_crop_recovers_fast_rep_ownership_in_original_coordinates(self):
        result,calls=self.detect(frames())
        owned=[r for r in result.values() if r['assigned']]
        self.assertGreater(len(owned),3)
        self.assertTrue(any(shape[:2] != (500,600) for shape in calls))
        self.assertTrue(all(r['assigned'][1]['box'][0] == 100 for r in owned))

    def test_stationary_person_does_not_trigger_extra_inference(self):
        result,calls=self.detect(frames(False))
        self.assertEqual(7,len(calls))
        self.assertTrue(all(not r['assigned'] for r in result.values()))

    def test_person_motion_does_not_confirm_stationary_bar(self):
        result,calls=self.detect(frames(),moving=False)
        self.assertGreater(len(calls),7)
        self.assertTrue(all(not r['assigned'] for r in result.values()))

    def test_recovery_budget_is_per_person_not_per_joint(self):
        poses=frames()
        for frame in poses:
            person=frame['athletes'][0]
            person['keypoints'].append(dict(person['keypoints'][0],joint='RightWrist'))
        targets=recovery_targets(poses)
        times=[poses[i]['timestampSeconds'] for i in targets]
        self.assertTrue(all(b-a >= .5 for a,b in zip(times,times[1:])))

    def test_empty_prompts_preserve_every_frame_without_loading_sam(self):
        poses=frames()
        with patch('vision.pipeline.SamVideoTracker') as tracker:
            result=track_objects('unused',poses,{}, {},Path('unused'),Path('.'),'cpu',lambda *args:None)
        tracker.assert_not_called()
        self.assertEqual([[] for _ in poses],result)

if __name__=='__main__': unittest.main()
