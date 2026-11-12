using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;
namespace MotionTrace.Tests;

public class MeasurementStabilityTests
{
    [Fact] public void NewVisibleFragmentAndReacquisitionDoNotJumpOrSplitSameBar()
    {
        PoseFrame[] frames=[
            new(0,[]){Shaft=new(1,2,[new(100,200,150,200)],.9,true,0,.03)},
            new(.03,[]){Shaft=new(2,2,[new(100,202,150,202),new(200,230,400,230)],.9,false,0,0)}];
        var samples=new ShaftTrajectoryProvider().Extract(frames,0,Joint.LeftWrist);
        Assert.Equal(samples[0].ContinuityId,samples[1].ContinuityId);
        Assert.Equal(2,samples[1].Position.Y-samples[0].Position.Y,6);
    }
    [Fact] public void DifferentBarOrLongGapDoesNotJoin()
    {
        PoseFrame[] frames=[
            new(0,[]){Shaft=new(1,2,[new(100,200,150,200)],.9,true,0,.03)},
            new(.5,[]){Shaft=new(2,2,[new(100,200,150,200)],.9,false,0,0)}];
        var samples=new ShaftTrajectoryProvider().Extract(frames,0,Joint.LeftWrist);
        Assert.NotEqual(samples[0].ContinuityId,samples[1].ContinuityId);
    }
    [Fact] public void BriefConfidenceLossCanBeBridgedButLongLossCannot()
    {
        MotionSample Sample(double t,double y,double confidence)=>new(0,t,new(50,y),new(50,y),confidence,AnalysisQuality.Good);
        var repaired=MotionGapRepair.FillShortGaps([Sample(0,100,.9),Sample(.033,900,.1),Sample(.066,110,.8)],1000);
        Assert.Equal(105,repaired[1].Position.Y,5);Assert.Equal(AnalysisQuality.Reduced,repaired[1].Quality);
        var longGap=MotionGapRepair.FillShortGaps([Sample(0,100,.9),Sample(.3,900,.1),Sample(.6,110,.8)],1000);
        Assert.Equal(.1,longGap[1].Confidence);
    }
    [Fact] public void SlowSetupDriftBeforeClearDropDoesNotExtendLowering()
    {
        var points=new List<BarbellSample>();
        for(int i=0;i<=240;i++)
        {
            double t=i/30.0;double y=t<1?100:t<2?100+(t-1)*10:t<4?110:t<5?110+(t-4)*100:t<6?210-(t-5)*100:110;
            points.Add(new(t,new(100,y),.9));
        }
        var rep=Assert.Single(MovementAnalyzer.AnalyzeSignal(points,ExerciseType.BenchPress,1000).Reps);
        Assert.InRange(rep.Start,3.8,4.15);Assert.InRange(rep.Lifting.Duration,.8,1.2);
    }
    [Fact] public void FullTrajectoryRemainsVisibleWhenNoCompleteRepExists()
    {
        MovementPoint[] points=[new(0,100,10,0),new(.1,101,10,0)];
        var series=Assert.Single(RepChartData.Create("video",new(points,[],""),new HashSet<int>(),MotionChartMetric.Velocity,MotionChartAxis.Time));
        Assert.Equal(2,series.Points.Count());Assert.Equal(.1,series.End);
    }
    [Fact] public void BrieflyUnknownOwnerDoesNotRejectContinuousMovingShaft()
    {
        var rep=new MovementRep(1,null,new(0,1,[],true));
        var frames=Enumerable.Range(1,8).Select(i=>new PoseFrame(i*.04,[]) {Shaft=new(1,i is 1 or 7?2:null,[new(0,0,100,0)],.9,true,-2,.04)}).ToArray();
        Assert.Single(ShaftRepGate.Apply(new([], [rep],""),frames,2,1000).Reps);
    }
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void UnrackDropIsExcludedAndMidDescentPauseIsRetained(bool pause)
    {
        var samples=new List<BarbellSample>();
        for(int i=0;i<=300;i++)
        {
            double t=i/30.0;
            double y=t<1?100:t<1.5?100+60*(t-1):t<4?130:
                t<4.5?130+100*(t-4):pause&&t<5.5?180:
                t<(pause?6:5)?180+100*(t-(pause?5.5:4.5)):
                t<(pause?7:6)?230-100*(t-(pause?6:5)):130;
            samples.Add(new(t,new(100,y),.9));
        }
        var rep=Assert.Single(MovementAnalyzer.AnalyzeSignal(samples,ExerciseType.BenchPress,1000).Reps);
        Assert.InRange(rep.Start,3.8,4.15);
        Assert.InRange(rep.Lowering!.Duration,pause?1.8:.8,pause?2.2:1.2);
    }
    [Fact] public void MultipleSelectedRepsEachShowTimesAndMaximumSpeed()
    {
        MovementPoint[] points=[new(0,100,-25,0),new(1,75,-25,0)];
        var text=RepMetricsPresenter.Describe([new(1,new(0,1,points,false),new(1,2,points,true)),new(2,null,new(3,4,points,true))],"Barbell");
        Assert.Contains("Rep 1",text);Assert.Contains("Rep 2",text);
        Assert.Equal(2,text.Split("Max lifting speed").Length-1);
        Assert.Equal(2,text.Split("Total").Length-1);
        Assert.Contains("Lowering  —",text);Assert.Contains("Barbell estimate",text);
    }
    [Fact] public void ContinuousSetupDriftDoesNotStartClearDescent()
    {
        var samples=Enumerable.Range(0,301).Select(i=> {
            double t=i/30.0;
            double y=t<1?100:t<4?100+10*(t-1):t<5?130+100*(t-4):t<6?230-100*(t-5):130;
            return new BarbellSample(t,new(100,y),.9);
        }).ToArray();
        var analysis=MovementAnalyzer.AnalyzeSignal(samples,ExerciseType.BenchPress,1000);
        var rep=Assert.Single(analysis.Reps);
        Assert.InRange(rep.Start,3.7,4.15);
        Assert.True(rep.PreparationSeconds>2);
        var chart=Assert.Single(RepChartData.Create("test",analysis,new HashSet<int>{1},MotionChartMetric.Height,MotionChartAxis.Time));
        Assert.Equal(rep.PreparationStart,chart.Start);
        Assert.Equal(rep.Start,chart.LoweringStart);
        Assert.Equal(rep.Lowering!.End,chart.LoweringEnd);
        Assert.Equal(rep.Lifting.Start,chart.LiftingStart);
    }
    [Fact] public void SlowInitialPressCountsAsLiftingRatherThanBottomPause()
    {
        var samples=Enumerable.Range(0,301).Select(i=> {
            double t=i/60.0;
            double y=t<1?100:t<2?100+100*(t-1):t<2.3?200-5*(t-2):t<3.3?198.5-98.5*(t-2.3):100;
            return new BarbellSample(t,new(100,y),.9);
        }).ToArray();
        var rep=Assert.Single(MovementAnalyzer.AnalyzeSignal(samples,ExerciseType.BenchPress,1000).Reps);
        Assert.InRange(rep.Lifting.Start,1.9,2.12);
    }
}
