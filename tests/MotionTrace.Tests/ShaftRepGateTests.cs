using MotionTrace.Core.Athletes;
using MotionTrace.Core.Motion;
namespace MotionTrace.Tests;
public class ShaftRepGateTests
{
    private static MovementAnalysis Candidate()=>new([], [new(1,new(0,1,[],false),new(1,2,[],true))],"");
    private static PoseFrame[] Frames(double dy,int? owner=1,bool reliable=true)=>Enumerable.Range(0,20).Select(i=>
        new PoseFrame(1.05+i*.04,[]) {Shaft=new(1,owner,[new(0,0,100,0)],.9,reliable,dy,.04)}).ToArray();
    [Fact] public void EmptyHandWristMovementWithStationaryBarDoesNotCount()=>Assert.Empty(ShaftRepGate.Apply(Candidate(),Frames(0),1,1000).Reps);
    [Fact] public void MovingShaftKeepsOriginalWristTiming()
    {
        var candidate=Candidate();var result=ShaftRepGate.Apply(candidate,Frames(-2),1,1000);
        Assert.Same(candidate.Reps[0].Lifting,Assert.Single(result.Reps).Lifting);
    }
    [Fact] public void OtherAthleteOrAmbiguousOwnerDoesNotConfirm()
    {
        Assert.Empty(ShaftRepGate.Apply(Candidate(),Frames(-2,2),1,1000).Reps);
        Assert.Empty(ShaftRepGate.Apply(Candidate(),Frames(-2,null),1,1000).Reps);
    }
    [Fact] public void MissingFlowOrDownwardMotionDoesNotConfirm()
    {
        Assert.Empty(ShaftRepGate.Apply(Candidate(),Frames(-2,reliable:false),1,1000).Reps);
        Assert.Empty(ShaftRepGate.Apply(Candidate(),Frames(2),1,1000).Reps);
    }
    [Fact] public void ReacquisitionJumpsCannotAccumulate()
    {
        var frames=Frames(-2).Select((f,i)=>f with {Shaft=f.Shaft! with {TrackId=i+1}}).ToArray();
        Assert.Empty(ShaftRepGate.Apply(Candidate(),frames,1,1000).Reps);
    }
}
