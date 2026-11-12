using MotionTrace.Core.Motion;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Athletes;
namespace MotionTrace.Tests;
public class PlaybackSynchronizationTests
{
 [Fact] public void CursorUsesExactTimeRatherThanFrameRate()
 {
  MovementPoint[] points=[new(3.40,20,100,0),new(3.47,27,100,0)];
  var point=PlaybackSampleLookup.At(points,3.420)!;Assert.Equal(3.420,point.Time);Assert.Equal(22,point.Y,5);
 }
 [Fact] public void ScrubbingBackwardsIsStateless()
 {
  MovementPoint[] p=[new(1,10,10,0),new(1.1,11,10,0)];PlaybackSampleLookup.At(p,1.09);Assert.Equal(10.2,PlaybackSampleLookup.At(p,1.02)!.Y,5);
 }
 [Fact] public void CursorDoesNotBridgeLostIntervals()=>Assert.Null(PlaybackSampleLookup.At([new(1,0,0,0),new(1.1,10,0,1)],1.05));
 [Fact] public void CursorDoesNotExtrapolate()=>Assert.Null(PlaybackSampleLookup.At([new(1,0,0,0)],1.01));
 [Fact] public void MissingDataDoesNotFinishASet()
 {
  var p=Enumerable.Range(0,10).Select(i=>new MovementPoint(i*.1,0,20,0)).ToArray();
  var states=MovementStatusTimeline.Build(p,5,1);Assert.Equal(ExerciseStatus.Performing,states[^1]);
 }
 [Fact] public void ShortPauseDoesNotFinishASet()
 {
  var p=Enumerable.Range(0,31).Select(i=>new MovementPoint(i*.1,0,i<10?20:0,0)).ToArray();
  Assert.Equal(ExerciseStatus.Performing,MovementStatusTimeline.Build(p,3,1)[^1]);
 }
 [Fact] public void WristProviderDoesNotUseLostOrOtherPerson()
 {
  var p=new AthletePose(1,new(0,0,100,200),.9,[new(Joint.LeftWrist,new(10,20),.9)]){TrackingState=TrackingState.Lost};
  Assert.Empty(new WristTrajectoryProvider().Extract([new(0,[p])],1,Joint.LeftWrist));
  Assert.Empty(new WristTrajectoryProvider().Extract([new(0,[p with {TrackingState=TrackingState.Tracked}])],2,Joint.LeftWrist));
 }
}
