using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;
namespace MotionTrace.Tests;
public class MovementAnalysisTests
{
    private static List<BarbellSample> Signal(params (double Time,double Y)[] knots)
    {
        var result=new List<BarbellSample>();
        for(int i=0;i<=Math.Round(knots[^1].Time*30);i++) {
            double t=i/30.0; int k=0;
            while(k+1<knots.Length-1 && knots[k+1].Time<t) k++;
            double f=(t-knots[k].Time)/(knots[k+1].Time-knots[k].Time);
            result.Add(new(t,new(100,knots[k].Y+f*(knots[k+1].Y-knots[k].Y)),.9));
        }
        return result;
    }
    private static MovementAnalysis Analyze(List<BarbellSample> samples,ExerciseType exercise=ExerciseType.BenchPress)=>MovementAnalyzer.AnalyzeSignal(samples,exercise,1000);
    [Fact] public void BackdatesClearDropAndSeparatesBottomPause()
    {
        var a=Analyze(Signal((0,100),(1,103),(2,100),(3,200),(3.5,200),(4.5,100),(5.2,100)));
        var r=Assert.Single(a.Reps);
        Assert.InRange(r.Start,1.8,2.15); Assert.InRange(r.Lowering!.End,2.8,3.15);
        Assert.InRange(r.Lifting.Start,3.3,3.7); Assert.InRange(r.End,4.3,4.7);
        Assert.InRange(r.PauseSeconds,.2,.8); Assert.InRange(r.Lifting.MeanSpeed,80,120);
    }
    [Fact] public void SmallTopWigglesDoNotCreateReps()=>Assert.Empty(Analyze(Signal((0,100),(1,105),(2,100),(3,104),(4,100))).Reps);
    [Fact] public void DeadliftDescentBelongsToPreviousLiftNotNextRep()
    {
        var signal=Signal((0,200),(1,200),(2,100),(2.6,100),(3.6,200),(4,200),(5,100),(5.6,100));
        var reps=Analyze(signal,ExerciseType.Deadlift).Reps;
        Assert.Equal(2,reps.Count);
        Assert.Equal(reps[0].Lifting.Start,reps[0].Start);
        Assert.True(reps[0].LoweringFollowsLifting);
        Assert.InRange(reps[0].Lowering!.Start,2.4,2.8);
        Assert.InRange(reps[0].Lowering!.End,3.4,3.8);
        Assert.Null(reps[1].Lowering);
        Assert.InRange(reps[1].Start,3.8,4.2);
    }
    [Fact] public void BenchDoesNotTreatInitialUpwardMovementAsRep()=>Assert.Empty(Analyze(Signal((0,200),(1,200),(2,100),(3,100))).Reps);
    [Fact] public void DeadliftPreparationMotionDoesNotExtendThePull()
    {
        var rep=Assert.Single(Analyze(Signal((0,200),(1,200),(1.3,190),(1.6,196),(2.5,196),(3.5,100),(4.2,100)),ExerciseType.Deadlift).Reps);
        Assert.InRange(rep.Lifting.Start,2.35,2.65);
    }
    [Fact] public void MissingPoseDoesNotJoinPhases()
    {
        var signal=Signal((0,100),(1,100),(2,200),(3,100),(4,100));
        Assert.Empty(Analyze(signal.Where(p=>p.TimestampSeconds<1.8 || p.TimestampSeconds>2.4).ToList()).Reps);
    }
    [Fact] public void CroppedPressRemainsIncomplete()=>Assert.Empty(Analyze(Signal((0,100),(1,100),(2,200),(3,130))).Reps);
    [Fact] public void MidPressPauseDoesNotEndRep()
    {
        var r=Assert.Single(Analyze(Signal((0,100),(1,100),(2,200),(2.5,160),(3.2,160),(4,100),(5,100))).Reps);
        Assert.InRange(r.End,3.8,4.2);
    }
    [Fact] public void ImmediateNextRepIsNotLost()
    {
        var reps=Analyze(Signal((0,100),(1,100),(2,200),(3,100),(4,200),(5,100),(6,100))).Reps;
        Assert.Equal(2,reps.Count);
    }
    [Fact] public void SpeedBenchSeriesDoesNotRequireBottomOrTopPauses()
    {
        // IMG_0809 has approximately .4 s descents and .47 s presses.
        var signal=Signal((0,100),(1,100),(1.4,200),(1.87,100),
            (2.27,200),(2.74,100),(3.14,200),(3.61,100),(4.2,100));
        var reps=Analyze(signal).Reps;
        Assert.Equal(3,reps.Count);
        foreach(var rep in reps)
        {
            Assert.InRange(rep.Lowering!.Duration,.25,.55);
            Assert.InRange(rep.Lifting.Duration,.3,.6);
            Assert.InRange(rep.PauseSeconds,0,.1);
        }
    }
    [Theory]
    [InlineData(.3)]
    [InlineData(.4)]
    public void MissingSpeedBenchBottomDoesNotInventRepOrPhase(double gap)
    {
        var signal=Signal((0,100),(1,100),(1.4,200),(1.87,100),(2.5,100));
        var observed=signal.Where(p=>p.TimestampSeconds<1.4-gap/2 || p.TimestampSeconds>1.4+gap/2).ToList();
        Assert.Empty(Analyze(observed).Reps);
    }
    [Fact] public void CompletedPressWithSmallRackingReversalBeforeVisibilityLossIsRetained()
    {
        var signal=Signal((0,100),(1,100),(1.4,200),(1.9,100),
            (2.3,200),(2.8,100),(2.9,100),(3.12,105));
        var reps=Analyze(signal).Reps;
        Assert.Equal(2,reps.Count);
        Assert.InRange(reps[1].Lifting.End,2.7,2.95);
    }
    [Fact] public void SmallReversalDuringPartialPressDoesNotConfirmLockout()
    {
        var signal=Signal((0,100),(1,100),(1.4,200),(1.9,120),(2,120),(2.25,125));
        Assert.Empty(Analyze(signal).Reps);
    }
    [Fact] public void RejectsInvalidInput()=>Assert.Throws<ArgumentOutOfRangeException>(()=>MovementAnalyzer.AnalyzeSignal([],ExerciseType.BenchPress,1000,double.NaN));
    [Fact] public void TimeIsIndependentOfSamplingDensity()
    {
        var signal=Signal((0,100),(1,100),(2,200),(2.5,200),(3.5,100),(4.2,100));
        var dense=Assert.Single(Analyze(signal).Reps);
        var sparse=Assert.Single(Analyze(signal.Where((_,i)=>i%3==0).ToList()).Reps);
        Assert.InRange(Math.Abs(dense.Start-sparse.Start),0,.15);
        Assert.InRange(Math.Abs(dense.End-sparse.End),0,.15);
    }
    [Fact] public void LowConfidenceDoesNotBridgeARep()
    {
        var signal=Signal((0,100),(1,100),(2,200),(3,100),(4,100))
            .Select(s=>s.TimestampSeconds is >1.8 and <2.4?s with { Confidence=.1 }:s).ToList();
        Assert.Empty(Analyze(signal).Reps);
    }
    [Fact] public void SquatAlsoStartsWithLowering()
    {
        var rep=Assert.Single(Analyze(Signal((0,100),(1,100),(2,200),(3,100),(4,100)),ExerciseType.Squat).Reps);
        Assert.NotNull(rep.Lowering);
    }
}
