import unittest
from comparison.seed_points import choose_points


class SeedPointsTests(unittest.TestCase):
    def test_image_refinement_stays_on_shaft_and_ignores_off_axis_texture(self):
        import numpy as np
        import cv2
        image=np.full((200,400,3),80,np.uint8)
        cv2.rectangle(image,(60,97),(68,103),(180,180,180),-1)
        cv2.rectangle(image,(330,97),(338,103),(180,180,180),-1)
        cv2.rectangle(image,(45,75),(75,88),(255,255,255),-1)
        points=choose_points([dict(line=[40,100,360,100],confidence=.9)],400,200,image)
        self.assertTrue(55 <= points[0]['x'] <= 75)
        self.assertTrue(325 <= points[1]['x'] <= 345)
        self.assertTrue(all(abs(p['y']-100)<=3 for p in points))

    def test_featureless_image_keeps_detector_suggestion(self):
        import numpy as np
        segments=[dict(line=[40,100,360,100],confidence=.9)]
        self.assertEqual(choose_points(segments,400,200),choose_points(segments,400,200,np.zeros((200,400,3),np.uint8)))

    def test_uses_strong_long_segment_in_source_coordinates(self):
        points = choose_points([
            dict(line=[20, 30, 200, 40], confidence=.8),
            dict(line=[1, 2, 15, 3], confidence=.99),
            dict(line=[0, 0, 300, 100], confidence=.2)], 300, 200)
        self.assertEqual([dict(x=20., y=30.), dict(x=200., y=40.)], points)

    def test_missing_or_invalid_detection_leaves_manual_selection(self):
        self.assertEqual([], choose_points([], 300, 200))
        self.assertEqual([], choose_points([dict(line=[0, 0, float('nan'), 20], confidence=.9)], 300, 200))
        self.assertEqual([], choose_points([dict(line=[-50,-50,-10,-10],confidence=.9)],300,200))
        self.assertEqual([], choose_points([dict(line=[0,0,200,20],confidence=float('nan'))],300,200))

    def test_endpoint_on_border_is_kept_inside_image(self):
        self.assertEqual(dict(x=299., y=199.), choose_points([
            dict(line=[0, 0, 300, 200], confidence=.9)], 300, 200)[1])
