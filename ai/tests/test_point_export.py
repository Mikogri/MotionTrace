import unittest
import numpy as np
from motiontrace_ai.export_video import draw

class PointExportTests(unittest.TestCase):
    def test_selected_point_only_tracker_exports_without_mask_or_box(self):
        image=np.zeros((64,64,3),np.uint8)
        frame=dict(Athletes=[dict(AthleteId=2,BoundingBox=dict(X=0,Y=0,Width=10,Height=10),TrackingState=0,Keypoints=[])],
            Objects=[dict(AthleteId=2,TrackingState="Tracked",Box=None,Measurement=dict(X=40,Y=40,IsProxy=False))])
        draw(image,frame)
        self.assertTrue(image[40,40].any())
        frame["Objects"][0]["AthleteId"]=3
        image[:]=0
        draw(image,frame)
        self.assertFalse(image[40,40].any())
