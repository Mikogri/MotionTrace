using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.Motion;
namespace MotionTrace.Tests;
public class ExportTests
{
    [Fact] public void DeadliftCsvSeparatesTopPauseFromBottomPauseAndExportsReturn()
    {
        MovementPoint[] points=[new(.5,150,-100,0),new(1.5,100,0,0),new(2.5,150,100,0)];
        var rep=new MovementRep(1,new(2,3,points,false),new(0,1,points,true));
        var analysis=new MovementAnalysis(points,[rep],"");
        using var samples=new StringWriter();
        MovementCsv.WriteSamples(samples,analysis);
        Assert.Contains(",lifting,",samples.ToString());
        Assert.Contains(",top_pause,",samples.ToString());
        Assert.Contains(",lowering,",samples.ToString());
        using var reps=new StringWriter();
        MovementCsv.WriteReps(reps,analysis);
        var lines=reps.ToString().Split(Environment.NewLine,StringSplitOptions.RemoveEmptyEntries);
        var columns=lines[0].Split(',');var values=lines[1].Split(',');
        Assert.Equal(columns.Length,values.Length);
        Assert.Equal("",values[Array.IndexOf(columns,"bottom_pause_s")]);
        Assert.Equal("1",values[Array.IndexOf(columns,"top_pause_s")]);
        Assert.Equal("1",values[Array.IndexOf(columns,"lifting_end_s")]);
        Assert.Equal("3",values[Array.IndexOf(columns,"end_s")]);
    }
    [Fact] public void SelectionRemovesOtherPeopleAndUnassignedShaftWithoutChangingOriginal() {
        var poses=new[]{new AthletePose(1,new(0,0,10,10),1,[]),new AthletePose(2,new(20,20,10,10),1,[])};
        var input=new AnalysisResult(1,new("test",1,100,100,30),new("a","b","c"),[new(1,"one"),new(2,"two")],
            [new(0,poses){Shaft=new(1,1,[],1,true,1,.03)},new(.03,poses){Shaft=new(1,2,[],1,true,1,.03)},new(.06,poses){Shaft=new(1,null,[],1,true,1,.03)}],[]);
        var output=AnalysisSelection.Filter(input,new HashSet<int>{2});
        Assert.Equal(2,Assert.Single(output.Athletes).Id);
        Assert.All(output.Frames,f=>Assert.Equal(2,Assert.Single(f.Athletes).AthleteId));
        Assert.Null(output.Frames[0].Shaft);Assert.NotNull(output.Frames[1].Shaft);Assert.Null(output.Frames[2].Shaft);
        Assert.Equal(2,input.Frames[0].Athletes.Count);
    }
    [Fact] public void CsvUsesInvariantNumbersAndExportsEverySampleWithoutInventingReps() {
        var prior=System.Globalization.CultureInfo.CurrentCulture;
        try {
            System.Globalization.CultureInfo.CurrentCulture=new("pl-PL");
            using var writer=new StringWriter();
            MovementCsv.WriteSamples(writer,new([new(.25,12.5,-4.5,0){FrameIndex=7}],[],""));
            Assert.Contains("0.25,7,0",writer.ToString());Assert.Contains("unclassified,12.5",writer.ToString());
            Assert.Equal(2,writer.ToString().Split(Environment.NewLine,StringSplitOptions.RemoveEmptyEntries).Length);
        } finally {System.Globalization.CultureInfo.CurrentCulture=prior;}
    }
}
