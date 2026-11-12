using MotionTrace.Core.Motion;

namespace MotionTrace.Tests;

public class RepChartTests
{
    private static MovementRep Rep(int number,double start,double seconds=1)
    {
        var points=Enumerable.Range(0,11).Select(i=>new MovementPoint(start+seconds*i/10,100-10*i,-100/seconds,0)).ToArray();
        return new(number,null,new(start,start+seconds,points,true));
    }
    [Fact] public void RemovingActiveRepMovesPlaybackActivationToASelectedRep()
    {
        var state=new RepSelectionState();state.Reset([1,2,3]);state.Activate(1);state.Toggle(3);
        Assert.Equal(1,state.ActiveRep);Assert.Equal(new[]{1,3},state.Selected.Order());
        state.Toggle(1);Assert.Equal(3,state.ActiveRep);Assert.Equal(new[]{3},state.Selected);
        state.SelectAll();Assert.Equal(3,state.Selected.Count);state.Clear();Assert.Null(state.ActiveRep);Assert.Empty(state.Selected);
    }
    [Fact] public void ReselectingRepsPreservesAllPhaseBoundaries()
    {
        MovementPoint[] points=[new(0,100,0,0),new(1,100,0,0),new(2,200,0,0),new(3,200,0,0),new(4,100,0,0)];
        var rep=new MovementRep(1,new(1,2,points,false),new(3,4,points,true)){PreparationStart=0};
        var analysis=new MovementAnalysis(points,[rep],"");var state=new RepSelectionState();state.Reset([1]);
        state.SelectAll();state.Clear();state.Toggle(1);
        var series=Assert.Single(RepChartData.Create("video",analysis,state.Selected,MotionChartMetric.Velocity,MotionChartAxis.Time));
        Assert.Equal(0,series.Start);Assert.Equal(1,series.LoweringStart);Assert.Equal(2,series.LoweringEnd);Assert.Equal(3,series.LiftingStart);
        Assert.Equal(1,state.ActiveRep);
    }
    [Fact] public void NewAnalysisDropsOldSelectionAndIgnoresUnknownIds()
    {
        var state=new RepSelectionState();state.Reset([1,2]);state.Activate(2);state.Reset([4]);state.Toggle(2);state.Activate(2);
        Assert.Empty(state.Selected);Assert.Null(state.ActiveRep);
    }
    [Fact] public void RomUsesDisplacementNotElapsedTime()
    {
        MovementPoint[] points=[new(10,100,0,0),new(10.1,90,-100,0),new(10.2,20,-100,0),new(10.3,0,0,0)];
        var rep=new MovementRep(1,null,new(10,10.3,points,true));
        var series=RepChartData.Create("A",new(points,[rep],""),new HashSet<int>{1},MotionChartMetric.Velocity,MotionChartAxis.Rom).Single();
        Assert.Same(points,series.Samples);Assert.Equal(new double[]{0,10,80,100},series.Points.Select(p=>p.X));
        Assert.Equal(45,series.At(10.15)!.Value.X,6);
    }
    [Fact] public void DifferentRepDurationsShareRomRangeAndUseIndependentTimeOrigins()
    {
        var a=Rep(1,5);var b=Rep(2,20,2);var data=new MovementAnalysis(a.Lifting.Points.Concat(b.Lifting.Points).ToArray(),[a,b],"");
        foreach(var axis in new[]{MotionChartAxis.Rom,MotionChartAxis.Time}) {
            var series=RepChartData.Create("video",data,new HashSet<int>{1,2},MotionChartMetric.Height,axis);
            Assert.Equal(0,series[0].Points.First().X);Assert.Equal(0,series[1].Points.First().X);
            Assert.Equal(axis==MotionChartAxis.Rom?100:1,series[0].Points.Last().X);
            Assert.Equal(axis==MotionChartAxis.Rom?100:2,series[1].Points.Last().X);
        }
    }
    [Fact] public void RomOmitsLoweringButTimeIncludesEntireRepWithoutCopyingAnalysis()
    {
        var up=Rep(1,5);MovementPoint[] down=[new(4,0,100,0),new(4.1,100,100,0)];
        var rep=up with{Lowering=new(4,4.1,down,false)};
        var analysis=new MovementAnalysis(down.Concat(up.Lifting.Points).ToArray(),[rep],"");
        var time=RepChartData.Create("A",analysis,new HashSet<int>{1},MotionChartMetric.Velocity,MotionChartAxis.Time).Single();
        var rom=RepChartData.Create("A",analysis,new HashSet<int>{1},MotionChartMetric.Velocity,MotionChartAxis.Rom).Single();
        Assert.Same(analysis.Points,time.Samples);Assert.Equal(4,time.Start);Assert.Equal(5,rom.Start);
        Assert.Null(rom.At(4));Assert.Null(time.At(4.5));Assert.NotNull(time.At(5.05));
    }
    [Fact] public void CursorHandlesBackwardSeekAndExcludesOtherRepTimes()
    {
        var rep=Rep(1,3);var series=RepChartData.Create("A",new(rep.Lifting.Points,[rep],""),new HashSet<int>{1},MotionChartMetric.Height,MotionChartAxis.Time).Single();
        Assert.Equal(.8,series.At(3.8)!.Value.X,6);Assert.Equal(.2,series.At(3.2)!.Value.X,6);
        Assert.Null(series.At(2.9));Assert.Null(series.At(4.1));
        Assert.NotNull(series.At(3-0.0000001));
        Assert.NotEqual(series.Id,(series with{SourceVideoId="B"}).Id);
    }
    [Fact] public void InsufficientTravelDoesNotProduceFakeRom()
    {
        MovementPoint[] points=[new(0,100,0,0),new(.1,100,0,0)];
        var series=new MotionChartSeries("A","1","Rep 1",points,0,.1,100,MotionChartMetric.Height,MotionChartAxis.Rom,100,100);
        Assert.Empty(series.Points);Assert.Null(series.At(.05));
    }
}
