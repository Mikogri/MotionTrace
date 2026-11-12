using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.PoseCorrection;
namespace MotionTrace.Tests;
public class PoseCorrectionTests
{
 private static AnalysisResult Data(Func<int,Joint,Keypoint,Keypoint>? change=null) => new(2,new("test",1,1000,1000,30),new("test","test","none"),[new(1,"Athlete 1")],
  Enumerable.Range(0,15).Select(i=>new PoseFrame(i/30.0,[new(1,new(0,0,600,800),.9,Enum.GetValues<Joint>().Select(j=> {
   var p=new Keypoint(j,new(j.ToString().StartsWith("Left")?100:400,100+(int)j*20),.9);
   return change?.Invoke(i,j,p)??p;
  }).ToArray())])).ToArray(),[]);
 private static AnalysisResult Correct(AnalysisResult input,int gap=3)=>new TemporalPoseCorrector(new(MaximumInterpolationFrames:gap),new LightPoseSmoother()).Correct(input);
 private static Keypoint Get(AnalysisResult r,int frame,Joint joint)=>r.Frames[frame].Athletes[0].Keypoints.Single(k=>k.Joint==joint);
 [Fact] public void IsolatedJumpIsFlaggedAndInterpolated()
 {
  var input=Data((i,j,p)=>i==7 && j==Joint.LeftKnee?new(j,new(800,50),.9):p);
  var k=Get(Correct(input),7,Joint.LeftKnee);Assert.True(k.IsOutlier);Assert.True(k.IsInterpolated);Assert.Equal(new Point2(800,50),k.RawPosition);Assert.InRange(k.Position.X,99,101);
 }
 [Fact] public void ShortGapFilledLongGapLeftMissing()
 {
  var shortGap=Correct(Data((i,j,p)=>i is 6 or 7 && j==Joint.LeftWrist?new(j,p.Position,0):p));
  Assert.True(Get(shortGap,6,Joint.LeftWrist).IsInterpolated);
  var longGap=Correct(Data((i,j,p)=>i>=4 && i<=9 && j==Joint.LeftWrist?new(j,p.Position,0):p));
  Assert.False(Get(longGap,6,Joint.LeftWrist).IsInterpolated);Assert.Equal(0,Get(longGap,6,Joint.LeftWrist).Confidence);
 }
 [Theory]
 [InlineData(1)]
 [InlineData(2)]
 [InlineData(3)]
 public void CorrectsShortLeftRightSwap(int length)
 {
  var baseline=Data();var input=Data((i,j,p)=>i>=6 && i<6+length && j is Joint.LeftWrist or Joint.RightWrist?
   new(j,Get(baseline,7,j==Joint.LeftWrist?Joint.RightWrist:Joint.LeftWrist).Position,.9):p);
  var k=Get(Correct(input),6,Joint.LeftWrist);Assert.True(k.IsCorrected);Assert.Equal(100,k.Position.X,1);
 }
 [Fact] public void LimbLengthSpikeIsRejected()
 {
  var input=Data((i,j,p)=>i==7 && j==Joint.LeftWrist?new(j,new(100,400),.9):p);
  Assert.True(Get(Correct(input),7,Joint.LeftWrist).IsOutlier);
 }
 [Fact] public void LostTrackIsNotInterpolated()
 {
  var raw=Data();var frames=raw.Frames.ToArray();frames[7]=new(frames[7].TimestampSeconds,[frames[7].Athletes[0] with {TrackingState=TrackingState.Lost,Keypoints=[]}]);
  Assert.Empty(Correct(raw with {Frames=frames}).Frames[7].Athletes[0].Keypoints);
 }
 [Fact] public void OcclusionReducesQuality()
 {
  var raw=Data();var result=Correct(raw with {Frames=raw.Frames.Select(f=>f with {Athletes=f.Athletes.Select(p=>p with {OcclusionRisk=OcclusionRisk.High}).ToArray()}).ToArray()});
  Assert.Equal(AnalysisQuality.Poor,result.Frames[7].Athletes[0].Quality);
  Assert.True(Get(result,7,Joint.LeftWrist).Confidence<Get(raw,7,Joint.LeftWrist).Confidence);
 }
 [Fact] public void CorrectionDoesNotMutateInput(){var input=Data();Correct(input);Assert.False(Get(input,7,Joint.LeftWrist).IsCorrected);}
}
