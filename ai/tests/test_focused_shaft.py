import unittest
import numpy as np
from motiontrace_ai.focused_shaft import FocusedShaftDetector


def pose(identity=1,x=200,y=200):
    return dict(athleteId=identity,trackingState='Tracked',boundingBox=dict(x=x,y=y,width=200,height=400))


def bar(identity=1,x=200,y=300):
    return dict(athleteId=identity,trackId=identity,confidence=.9,
                segments=[dict(x1=x-40,y1=y,x2=x+240,y2=y)])


class Detector:
    def __init__(self,results):self.results=iter(results);self.shapes=[]
    def detect(self,image):self.shapes.append(image.shape);return next(self.results)


class FocusedShaftTests(unittest.TestCase):
    def test_moving_crop_does_not_move_stationary_bar_coordinates(self):
        focus=FocusedShaftDetector(None)
        image=np.zeros((1000,1200,3),np.uint8)
        expected=[160,300,440,300]
        for time,x in [(0,200),(.1,220),(.2,240)]:
            focus.prepare(time,[pose(x=x)],[bar()])
            bounds,_=focus._crop(1,focus.regions[1],1200,1000)
            # A second _crop call during detect can shrink the box, so use a
            # detector returning an image-marked line in actual crop coordinates.
            image[:]=0
            image[300,160:441]=255
            class ImageDetector:
                def detect(self,im):
                    yy,xx=np.where(im[:,:,0]>0)
                    return [dict(line=[float(xx.min()),float(yy[0]),float(xx.max()),float(yy[0])],confidence=.95)]
            focus.detector=ImageDetector()
            actual=focus.detect(image)
            np.testing.assert_array_equal(actual[0]['line'],expected)

    def test_crop_follows_retreat_and_contains_person_and_bar(self):
        focus=FocusedShaftDetector(None)
        focus.prepare(0,[pose()],[bar()])
        first,_=focus._crop(1,focus.regions[1],1200,1000)
        focus.prepare(.1,[pose(x=350,y=230)],[bar()])
        second,expected=focus._crop(1,focus.regions[1],1200,1000)
        self.assertGreater(second[2],first[2])
        self.assertGreater(second[3],first[3])
        self.assertLessEqual(second[0],350)
        self.assertGreaterEqual(second[2],550)
        self.assertAlmostEqual(expected[0]['line'][0],310)
        self.assertAlmostEqual(expected[0]['line'][1],330)

    def test_two_pairs_have_independent_regions_and_missing_owner_expires(self):
        focus=FocusedShaftDetector(None)
        focus.prepare(0,[pose(),pose(2,800)],[bar(),bar(2,800)])
        a,_=focus._crop(1,focus.regions[1],1400,1000)
        b,_=focus._crop(2,focus.regions[2],1400,1000)
        self.assertLess(a[2],b[0])
        focus.prepare(1,[],[])
        self.assertEqual(focus.regions,{})

    def test_crop_loss_expands_search_region(self):
        focus=FocusedShaftDetector(None)
        focus.prepare(0,[pose()],[bar()]);a,_=focus._crop(1,focus.regions[1],1200,1000)
        focus.prepare(.5,[pose()],[]);b,_=focus._crop(1,focus.regions[1],1200,1000)
        self.assertLess(b[0],a[0]);self.assertGreater(b[2],a[2])

    def test_local_coordinates_return_to_original_image(self):
        focus=FocusedShaftDetector(None);focus.prepare(0,[pose()],[bar()])
        bounds,_=focus._crop(1,focus.regions[1],1200,1000);x,y=bounds[:2]
        global_line=dict(line=[160,300,440,300],confidence=.9)
        local_line=dict(line=[160-x,300-y,440-x,300-y],confidence=.95)
        detector=Detector([[global_line],[local_line]]);focus.detector=detector
        result=focus.detect(np.zeros((1000,1200,3),np.uint8))
        np.testing.assert_array_equal(result[0]['line'],global_line['line'])
        self.assertEqual(len(result),1)
        self.assertEqual(focus.statistics['localAccepted'],1)
        self.assertLess(detector.shapes[1][0]*detector.shapes[1][1],1200000)

    def test_local_background_bar_cannot_replace_global_detection(self):
        global_line=dict(line=[160,300,440,300],confidence=.9)
        focus=FocusedShaftDetector(None);focus.prepare(0,[pose()],[bar()])
        bounds,_=focus._crop(1,focus.regions[1],1200,1000);x,y=bounds[:2]
        focus.detector=Detector([[global_line],[dict(line=[160-x,450-y,440-x,450-y],confidence=.99)]])
        result=focus.detect(np.zeros((1000,1200,3),np.uint8))
        self.assertEqual(result,[global_line]);self.assertEqual(focus.statistics['localAccepted'],0)

    def test_discovery_runs_without_confirmed_pairs(self):
        detector=Detector([[],[]]);focus=FocusedShaftDetector(detector)
        focus.prepare(0,[pose()],[])
        image=np.zeros((1000,1200,3),np.uint8)
        focus.detect(image);focus.detect(image)
        self.assertEqual(focus.statistics,dict(fullCalls=2,localCalls=0,localAccepted=0))
