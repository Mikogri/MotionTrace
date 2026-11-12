import unittest
from unittest.mock import patch
import numpy as np
from motiontrace_ai.export_video import draw


class ExportSelectionTests(unittest.TestCase):
    def test_multiple_bars_only_draw_selected_owners(self):
        pose=dict(AthleteId=1,BoundingBox=dict(X=0,Y=0,Width=20,Height=20),TrackingState=0,Keypoints=[])
        def bar(owner,x):return dict(AthleteId=owner,MotionReliable=True,Segments=[dict(X1=x,Y1=10,X2=x+5,Y2=10)])
        frame=dict(Athletes=[pose],Shafts=[bar(1,10),bar(2,30),bar(None,50)])
        with patch('motiontrace_ai.export_video.cv2.line') as line:
            draw(np.zeros((100,100,3),np.uint8),frame)
            self.assertEqual(line.call_count,1)
            self.assertEqual(line.call_args.args[1],(10,10))

    def test_schema_four_selected_objects_and_lost_measurement(self):
        pose=dict(athleteId=1,boundingBox=dict(x=0,y=0,width=20,height=20),trackingState='Tracked',
                  keypoints=[dict(joint='Nose',x=5,y=6,confidence=.9)])
        def obj(owner,state='Tracked'):
            return dict(athleteId=owner,trackingState=state,box=dict(x=10,y=20,width=8,height=4),
                        measurement=dict(x=14,y=22,isProxy=True))
        lost=dict(athleteId=1,trackingState='Lost',box=None,measurement=None)
        frame=dict(athletes=[pose],shafts=[],objects=[obj(1),obj(2),lost])
        with patch('motiontrace_ai.export_video.cv2.drawMarker') as marker:
            draw(np.zeros((100,100,3),np.uint8),frame)
            self.assertEqual(marker.call_count,1)
            self.assertEqual(marker.call_args.args[1],(14,22))
