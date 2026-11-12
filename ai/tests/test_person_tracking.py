import unittest
from motiontrace_ai.person_tracking import PersonTracker, StableCrop
def d(x,a=None): return dict(box=[x,0,x+100,200],confidence=.9,appearance=a or [1.,0.])
class PersonTrackingTests(unittest.TestCase):
 def established(self, detection=None):
  t=PersonTracker()
  for time in (0.,.1,.2):t.update([d(0) if detection is None else detection],time)
  t.update([],.3)
  return t
 def test_established_person_recovers_after_one_second_occlusion(self):
  old=dict(box=[954.21,1475.02,1855.09,2711.48],confidence=.9,appearance=[.7,.3])
  returned=dict(box=[929.47,1666.56,2160.23,2712.2],confidence=.9,appearance=[.607,.393])
  t=self.established(old)
  # Geometry and elapsed gap from the bench track split; representative histogram distance.
  m,_=t.update([returned],.2+31/30)
  self.assertEqual([1],[track.identity for track,_ in m])
 def test_extended_recovery_rejects_different_appearance(self):
  t=self.established();m,_=t.update([d(0,[.7,.3])],1.3)
  self.assertNotIn(1,[track.identity for track,_ in m])
 def test_extended_recovery_does_not_extrapolate_stale_box_velocity(self):
  old=dict(box=[954.2102,1475.0190,1855.0879,2711.4849],confidence=.9,appearance=[.7,.3])
  returned=dict(box=[929.4706,1666.5568,2160.2339,2712.1997],confidence=.756,appearance=[.597366,.402634])
  t=self.established(old)
  # Snapshot of detector-box velocity before the real bench occlusion. It is
  # stale box-shape jitter, not evidence the lifter travelled left off the bench.
  t.tracks[0].velocity=(-949.9936,-231.1366)
  m,_=t.update([returned],.2+31/30)
  self.assertEqual([1],[track.identity for track,_ in m])
 def test_extended_recovery_requires_strong_overlap(self):
  t=self.established();m,_=t.update([d(50)],1.3)
  self.assertNotIn(1,[track.identity for track,_ in m])
 def test_extended_recovery_rejects_ambiguous_detections(self):
  t=self.established();m,_=t.update([d(-2),d(2)],1.3)
  self.assertNotIn(1,[track.identity for track,_ in m])
 def test_extended_recovery_requires_established_track(self):
  t=PersonTracker();t.update([d(0)],0);m,_=t.update([d(0)],1.1)
  self.assertNotIn(1,[track.identity for track,_ in m])
 def test_extended_recovery_expires_after_two_seconds(self):
  t=self.established();m,_=t.update([d(0)],2.21)
  self.assertEqual([2],[track.identity for track,_ in m])
 def test_extended_recovery_requires_appearance(self):
  detection=d(0);detection['appearance']=[]
  t=self.established(detection);m,_=t.update([detection],1.3)
  self.assertNotIn(1,[track.identity for track,_ in m])
 def test_reordered(self):
  t=PersonTracker();t.update([d(0),d(300)],0);m,_=t.update([d(302),d(2)],.03);self.assertEqual({302:2,2:1},{det["box"][0]:v.identity for v,det in m})
 def test_recovery(self):
  t=PersonTracker()
  for i in range(3):t.update([d(i)],i*.03)
  _,lost=t.update([],.1);self.assertEqual('Lost',lost[0].state)
  m,_=t.update([d(3)],.2);self.assertEqual(1,m[0][0].identity)
 def test_replacement(self):
  t=PersonTracker()
  for i in range(3):t.update([d(0)],i*.03)
  t.update([],.1);m,lost=t.update([d(0,[0.,1.])],.2);self.assertFalse(m);self.assertEqual(1,lost[0].identity)
 def test_ambiguity(self):
  t=PersonTracker()
  for i in range(3):t.update([d(0),d(130)],i*.03)
  m,lost=t.update([d(65)],.1);self.assertFalse(m);self.assertEqual(2,len(lost))
 def test_crop(self):
  c=StableCrop(.2);c.update(1,[100,100,200,300],0,500,500);b=c.update(1,[110,100,210,300],.03,500,500)
  self.assertLess(b[0],110);self.assertGreaterEqual(b[2],210);self.assertGreaterEqual(b[1],0)
