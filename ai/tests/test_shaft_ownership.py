import unittest
from motiontrace_ai.shaft_ownership import ShaftOwnership


def pose(identity,x,y):
    def joint(name,px,py):return dict(joint=name,x=px,y=py,confidence=.95)
    return dict(athleteId=identity,trackingState='Tracked',keypoints=[
        joint('LeftWrist',x,y),joint('RightWrist',x+80,y),
        joint('LeftShoulder',x+10,y+30),joint('RightShoulder',x+50,y+30),
        joint('LeftHip',x+100,y+35),joint('RightHip',x+140,y+35)])


def shaft(identity,x,y,delta=2):
    return dict(trackId=identity,athleteId=None,segments=[dict(x1=x-10,y1=y,x2=x+90,y2=y)],
                confidence=.9,motionReliable=True,deltaY=delta,deltaSeconds=.05)


class OwnershipTests(unittest.TestCase):
    def test_observed_bar_survives_bounded_pose_gap_confirmed_by_same_owner(self):
        for returning, duration, ambiguous in [(1,1.2,False),(2,1.2,False),(1,3.0,False),(1,1.2,True)]:
            with self.subTest(returning=returning,duration=duration,ambiguous=ambiguous):
                frames=[]
                for i in range(round(duration*10)+1):
                    end=i==round(duration*10)
                    p=pose(returning if end else 1,40,100)
                    p['boundingBox']=dict(x=0,y=0,width=300,height=300)
                    s=shaft(1,40,100+i)
                    s['athleteId']=returning if end else 1 if i==0 else None
                    s['ownershipAmbiguous']=ambiguous and i==5
                    frames.append(dict(timestampSeconds=i*.1,athletes=[p] if i==0 or end else [],shafts=[s]))
                ShaftOwnership().complete_gaps(frames,1000)
                expected=1 if returning==1 and duration<2 and not ambiguous else None
                self.assertEqual(expected,frames[6]['shafts'][0]['athleteId'])

    def test_confirmation_recovers_continuous_observed_preparation(self):
        tracker=ShaftOwnership();frames=[]
        for i in range(31):
            p=pose(1,40,100);p['boundingBox']=dict(x=0,y=0,width=300,height=300)
            s=shaft(1,40,100);s['athleteId']=1 if i==30 else None
            frames.append(dict(timestampSeconds=i*.1,athletes=[p],shafts=[s]))
        tracker.complete_gaps(frames,1000)
        self.assertTrue(all(f['shafts'][0]['athleteId']==1 for f in frames))

    def test_pose_gap_cannot_bridge_a_missing_bar(self):
        frames=[]
        for i in range(13):
            p=pose(1,40,100);p['boundingBox']=dict(x=0,y=0,width=300,height=300)
            s=shaft(1,40,100);s['athleteId']=1 if i in (0,12) else None
            frames.append(dict(timestampSeconds=i*.1,athletes=[p] if i in (0,12) else [],
                               shafts=[] if i in (4,5) else [s]))
        ShaftOwnership().complete_gaps(frames,1000)
        self.assertIsNone(frames[6]['shafts'][0]['athleteId'])

    def test_gap_between_different_owners_remains_unknown(self):
        tracker=ShaftOwnership();frames=[]
        for time,owner in [(0,1),(.1,None),(.2,2)]:
            p=pose(1,40,100);p['boundingBox']=dict(x=0,y=0,width=300,height=300)
            s=shaft(1,40,100);s['athleteId']=owner
            frames.append(dict(timestampSeconds=time,athletes=[p],shafts=[s]))
        tracker.complete_gaps(frames,1000)
        self.assertIsNone(frames[1]['shafts'][0]['athleteId'])

    def test_gap_does_not_restore_ambiguous_pair(self):
        tracker=ShaftOwnership();frames=[]
        for time,owner in [(0,1),(.1,None),(.2,1)]:
            p=pose(1,40,100);p['boundingBox']=dict(x=0,y=0,width=300,height=300)
            s=shaft(1,40,100);s['athleteId']=owner;s['ownershipAmbiguous']=owner is None
            frames.append(dict(timestampSeconds=time,athletes=[p],shafts=[s]))
        tracker.complete_gaps(frames,1000)
        self.assertIsNone(frames[1]['shafts'][0]['athleteId'])

    def test_two_moving_pairs_and_background_person(self):
        tracker=ShaftOwnership(); frames=[]
        for i in range(25):
            y=100+i*2
            bars=[shaft(1,40,y),shaft(2,400,250-i*2,-2)]
            tracker.update(i*.05,bars,[pose(10,40,y),pose(20,400,250-i*2),pose(30,700,100)],1000)
            frames.append(bars)
        self.assertEqual(tracker.participants,{10,20})
        self.assertTrue(all([s['athleteId'] for s in f]==[10,20] for f in frames))

    def test_stationary_bar_and_camera_only_motion_do_not_confirm(self):
        for moving in (False,True):
            tracker=ShaftOwnership()
            for i in range(25):
                y=100+i*2 if moving else 100
                bars=[shaft(1,40,y,0)]
                tracker.update(i*.05,bars,[pose(10,40,y)],1000)
            self.assertEqual(tracker.participants,set())

    def test_nearby_person_with_different_motion_does_not_own_bar(self):
        tracker=ShaftOwnership()
        for i in range(25):
            bars=[shaft(1,40,100+i)]
            tracker.update(i*.05,bars,[pose(10,40,100)],1000)
        self.assertEqual(tracker.participants,set())

    def test_identical_people_are_ambiguous_and_do_not_confirm(self):
        tracker=ShaftOwnership()
        for i in range(25):
            y=100+i*2
            bars=[shaft(1,40,y)]
            tracker.update(i*.05,bars,[pose(10,40,y),pose(20,40,y)],1000)
        self.assertEqual(tracker.participants,set())

    def test_confirmed_owner_survives_crossing_person_but_not_missing_pose(self):
        tracker=ShaftOwnership()
        for i in range(25):
            y=100+i*2; bars=[shaft(1,40,y)]
            tracker.update(i*.05,bars,[pose(10,40,y)],1000)
        for i in range(25,35):
            y=100+i*2; bars=[shaft(1,40,y)]
            tracker.update(i*.05,bars,[pose(10,40,y),pose(20,40,y)],1000)
            self.assertEqual(bars[0]['athleteId'],10)
        bars=[shaft(1,40,170)]
        tracker.update(1.75,bars,[],1000)
        self.assertIsNone(bars[0]['athleteId'])

    def test_one_athlete_cannot_own_two_equal_bars(self):
        tracker=ShaftOwnership()
        for i in range(25):
            y=100+i*2; bars=[shaft(1,40,y),shaft(2,40,y+1)]
            tracker.update(i*.05,bars,[pose(10,40,y)],1000)
        self.assertEqual(tracker.participants,set())
