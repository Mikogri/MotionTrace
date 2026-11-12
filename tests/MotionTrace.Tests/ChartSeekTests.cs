using MotionTrace.Core.Motion;
namespace MotionTrace.Tests;
public class ChartSeekTests
{
    [Fact] public void TimeSeekUsesAbsoluteVideoTimeIncludingPreparationAndClampsToRep() {
        var series=new MotionChartSeries("video","2","Rep 2",[],35,42,0,MotionChartMetric.Height,MotionChartAxis.Time);
        Assert.Equal(37.5,series.TimestampAtX(2.5,0));
        Assert.Equal(35,series.TimestampAtX(-10,0));Assert.Equal(42,series.TimestampAtX(100,0));
        Assert.Null(series.TimestampAtX(double.NaN,0));
    }
    [Fact] public void RomSeekMapsHeightToSampleTimeAndRejectsMissingRom() {
        MovementPoint[] points=[new(10,200,0,0),new(11,150,-50,0),new(12,100,-50,0)];
        var series=new MotionChartSeries("v","1","Rep 1",points,10,12,200,MotionChartMetric.Velocity,MotionChartAxis.Rom,200,100);
        Assert.Equal(11,series.TimestampAtX(50,10));
        Assert.Null((series with {RomTop=200}).TimestampAtX(50,10));
    }
    [Fact] public void PhaseFilterHidesPreparationAndDoesNotSeekIntoIt() {
        MovementPoint[] points=[new(0,100,0,0),new(1,100,0,0),new(2,200,0,0),new(3,100,0,0)];
        var series=new MotionChartSeries("v","1","Rep 1",points,0,3,200,MotionChartMetric.Height,MotionChartAxis.Time){LoweringStart=1,LoweringEnd=2,LiftingStart=2.5,VisiblePhases=14};
        Assert.DoesNotContain(series.Points,p=>p.Timestamp<1);Assert.Null(series.At(0));Assert.Equal(1,series.TimestampAtX(0,0));
        Assert.Empty((series with {VisiblePhases=0}).Points);Assert.Null((series with {VisiblePhases=0}).TimestampAtX(1,0));
    }
    [Fact] public void DeadliftChartIncludesReturnButRomContainsOnlyLifting()
    {
        MovementPoint[] points=[new(0,200,0,0),new(1,100,-100,0),new(2,100,0,0),new(3,200,100,0)];
        var rep=new MovementRep(1,new(2,3,points,false),new(0,1,points,true));
        var analysis=new MovementAnalysis(points,[rep],"");
        var time=Assert.Single(RepChartData.Create("v",analysis,new HashSet<int>{1},MotionChartMetric.Height,MotionChartAxis.Time));
        Assert.Equal(3,time.End);Assert.Equal(3,time.PhaseAt(.5));Assert.Equal(2,time.PhaseAt(1.5));Assert.Equal(1,time.PhaseAt(2.5));
        var rom=Assert.Single(RepChartData.Create("v",analysis,new HashSet<int>{1},MotionChartMetric.Height,MotionChartAxis.Rom));Assert.Equal(1,rom.End);
    }
}
