import unittest
from unittest.mock import patch
import cv2,numpy as np
from motiontrace_ai.shaft_tracking import flow,ShaftTracker,associate,compatible_fragments

class Detector:
    def detect(self,image):return [dict(line=[50.,100.,250.,100.],confidence=.9)]

class ShaftTrackingTests(unittest.TestCase):
    def test_bench_spotter_below_hips_does_not_steal_lying_lifters_bar(self):
        def point(j,x,y):return dict(joint=j,x=x,y=y,confidence=.9)
        lying=dict(athleteId=1,trackingState='Tracked',keypoints=[point('LeftWrist',80,96),point('RightWrist',220,96),point('LeftShoulder',100,100),point('RightShoulder',110,100),point('LeftHip',150,105),point('RightHip',160,105)])
        spotter=dict(athleteId=2,trackingState='Tracked',keypoints=[point('LeftWrist',80,100),point('RightWrist',220,100),point('LeftShoulder',100,20),point('RightShoulder',110,20),point('LeftHip',100,90),point('RightHip',110,90)])
        self.assertEqual(associate(Detector().detect(None),[lying,spotter],200),1)
        for pose in (lying,spotter):pose['boundingBox']=dict(x=50,y=10,width=200,height=150)
        tracker=ShaftTracker(Detector());image=np.zeros((200,300,3),np.uint8)
        self.assertEqual(tracker.update(image,0,[lying,spotter])['athleteId'],1)
        self.assertIsNone(tracker.update(image,.03,[spotter])['athleteId'])
        self.assertEqual(tracker.update(image,2.1,[spotter])['athleteId'],2)

    def test_short_detector_miss_uses_flow_but_expires(self):
        class MissingDetector:
            def __init__(self):self.calls=0
            def detect(self,image):
                self.calls+=1
                return Detector().detect(image) if self.calls==1 else []
        image=np.zeros((200,300,3),np.uint8)
        tracker=ShaftTracker(MissingDetector())
        with patch('motiontrace_ai.shaft_tracking.flow',return_value=np.zeros(2)):
            first=tracker.update(image,0,[])
            short=tracker.update(image,.1,[])
            self.assertEqual(first['trackId'],short['trackId'])
            self.assertFalse(short['motionReliable'])
            self.assertIsNone(tracker.update(image,.21,[]))

    def test_squat_grip_near_shoulder_can_own_bar(self):
        def point(j,x,y):return dict(joint=j,x=x,y=y,confidence=.9)
        p=dict(athleteId=3,trackingState='Tracked',keypoints=[point('LeftWrist',80,108),point('RightWrist',220,108),point('LeftShoulder',100,100),point('RightShoulder',180,100),point('LeftHip',110,160),point('RightHip',170,160)])
        self.assertEqual(associate(Detector().detect(None),[p],200),3)

    def test_deadlift_hands_below_hips_can_own_bar(self):
        def point(j,x,y):return dict(joint=j,x=x,y=y,confidence=.9)
        p=dict(athleteId=3,trackingState='Tracked',keypoints=[point('LeftWrist',80,100),point('RightWrist',220,100),point('LeftShoulder',100,20),point('RightShoulder',180,20),point('LeftHip',110,70),point('RightHip',170,70)])
        self.assertEqual(associate(Detector().detect(None),[p],200),3)
        p['keypoints']=p['keypoints'][1:]
        self.assertIsNone(associate(Detector().detect(None),[p],200))

    def test_fragment_reacquisition_rejects_remote_parallel_bar(self):
        segment=lambda line:[dict(line=line,confidence=.9)]
        self.assertTrue(compatible_fragments(segment([50,100,100,100]),segment([105,102,180,102]),200))
        self.assertFalse(compatible_fragments(segment([50,100,100,100]),segment([200,100,250,100]),200))
        self.assertFalse(compatible_fragments(segment([50,100,100,100]),segment([50,130,100,130]),200))

    def test_translation_flow(self):
        random=np.random.default_rng(4);im=random.integers(0,255,(200,300),dtype=np.uint8)
        moved=cv2.warpAffine(im,np.float32([[1,0,0],[0,1,-3]]),(300,200))
        delta=flow(im,moved,np.full_like(im,255));self.assertIsNotNone(delta);self.assertAlmostEqual(float(delta[1]),-3,delta=.15)
    def test_camera_translation_is_not_bar_motion(self):
        random=np.random.default_rng(4);im=random.integers(0,255,(200,300,3),dtype=np.uint8)
        tracker=ShaftTracker(Detector());first=tracker.update(im,0,[]);self.assertFalse(first['motionReliable'])
        moved=cv2.warpAffine(im,np.float32([[1,0,0],[0,1,-2]]),(300,200))
        second=tracker.update(moved,.03,[]);self.assertTrue(second['motionReliable']);self.assertAlmostEqual(second['deltaY'],0,delta=.3)
    def test_gap_does_not_measure_displacement(self):
        im=np.zeros((200,300,3),np.uint8);t=ShaftTracker(Detector());a=t.update(im,0,[]);b=t.update(im,.3,[])
        self.assertFalse(b['motionReliable']);self.assertGreater(b['trackId'],a['trackId'])
    def test_ambiguous_person_is_not_assigned(self):
        def pose(n):return dict(athleteId=n,trackingState='Tracked',keypoints=[dict(joint=j,x=x,y=100,confidence=.9) for j,x in [('LeftWrist',80),('RightWrist',220)]]+[dict(joint='LeftShoulder',x=150,y=130,confidence=.9)])
        s=Detector().detect(None);self.assertEqual(associate(s,[pose(1)],200),1);self.assertIsNone(associate(s,[pose(1),pose(2)],200))
        spotter=pose(2);spotter['keypoints'][-1]['y']=20
        self.assertEqual(associate(s,[pose(1),spotter],200),1)
        one=pose(1);one['keypoints']=one['keypoints'][1:]
        self.assertEqual(associate(s,[one],200),1)
        one['keypoints'][0]['confidence']=.5;self.assertIsNone(associate(s,[one],200))

if __name__=='__main__':unittest.main()
