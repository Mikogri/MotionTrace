using MotionTrace.Core.Athletes;
using MotionTrace.Core.Motion;

namespace MotionTrace.Tests;

public class ShaftContinuityTests
{
    [Fact]
    public void SameVerifiedBarReacquiredAcrossBriefOcclusionRetainsMeasuredEndpoints()
    {
        PoseFrame[] frames=[Frame(0,1,2,new(100,200,400,200)),new(.1,[]),
            Frame(.233,1,2,new(110,220,410,220))];
        var samples=new ShaftTrajectoryProvider().Extract(frames,2,Joint.LeftWrist);
        Assert.Equal(2,samples.Count);
        Assert.Equal(samples[0].ContinuityId,samples[1].ContinuityId);
        Assert.Equal(20,samples[1].Position.Y-samples[0].Position.Y,6);
        Assert.Equal(AnalysisQuality.Reduced,samples[1].Quality);
        Assert.False(samples[1].IsInterpolated);
    }

    [Theory]
    [InlineData(.3,1,2)]
    [InlineData(.233,2,2)]
    [InlineData(.233,1,null)]
    [InlineData(.233,1,3)]
    public void LongerOrUnverifiedReacquisitionDoesNotJoin(double time,int track,int? owner)
    {
        PoseFrame[] frames=[Frame(0,1,2,new(100,200,400,200)),Frame(time,track,owner,new(110,220,410,220))];
        var samples=new ShaftTrajectoryProvider().Extract(frames,0,Joint.LeftWrist);
        Assert.NotEqual(samples[0].ContinuityId,samples[1].ContinuityId);
    }

    [Fact]
    public void ObservedOwnershipTransferInterruptsTheSelectedAthletesTrajectory()
    {
        PoseFrame[] frames=[Frame(0,1,2,new(100,200,400,200)),
            Frame(.1,1,3,new(100,210,400,210)),Frame(.2,1,2,new(100,220,400,220))];
        var samples=new ShaftTrajectoryProvider().Extract(frames,2,Joint.LeftWrist);
        Assert.Equal(2,samples.Count);
        Assert.NotEqual(samples[0].ContinuityId,samples[1].ContinuityId);
    }

    private static PoseFrame Moving(double time,double y,int? owner=null) => new(time,[])
    {
        Shaft=new(1,owner,[new(100,y,200,y)],.9,true,25,.04)
    };

    [Fact]
    public void FastDescentReacquiresUnknownBarAcrossOneMissingFrameUsingMeasuredOverlap()
    {
        PoseFrame[] frames=[Moving(0,100),Moving(.04,125),Moving(.08,150),new(.12,[]),
            Frame(.16,2,null,new(100,202,200,202))];
        var samples=new ShaftTrajectoryProvider().Extract(frames,0,Joint.LeftWrist);
        Assert.Single(samples.Select(s=>s.ContinuityId).Distinct());
        Assert.Equal(52,samples[^1].Position.Y-samples[^2].Position.Y,6);
        Assert.Equal(AnalysisQuality.Reduced,samples[^1].Quality);
        Assert.DoesNotContain(samples,s=>s.TimestampSeconds==.12);
    }

    [Theory]
    [InlineData(250,250,null)] // Excess displacement.
    [InlineData(98,98,null)] // Opposite direction.
    [InlineData(180,224,null)] // Wrong angle even though midpoint would fit.
    [InlineData(202,202,3)] // Another known athlete.
    public void FastMotionCannotBridgeJumpAngleOrIdentityConflict(double y1,double y2,int? owner)
    {
        PoseFrame[] frames=[Moving(0,100,2),Moving(.04,125,2),Moving(.08,150,2),
            Frame(.16,2,owner,new(100,y1,200,y2))];
        var samples=new ShaftTrajectoryProvider().Extract(frames,0,Joint.LeftWrist);
        Assert.NotEqual(samples[^2].ContinuityId,samples[^1].ContinuityId);
    }

    [Fact]
    public void FastMotionChoosesConsistentFragmentInsteadOfLongerFalseFragment()
    {
        PoseFrame[] frames=[Moving(0,100,2),Moving(.04,125,2),Moving(.08,150,2),
            new(.16,[]){Shaft=new(2,2,[new(100,230,200,230),new(120,201,190,201)],.9,false,0,0)}];
        var samples=new ShaftTrajectoryProvider().Extract(frames,0,Joint.LeftWrist);
        Assert.Single(samples.Select(s=>s.ContinuityId).Distinct());
        Assert.Equal(51,samples[^1].Position.Y-samples[^2].Position.Y,6);
    }

    [Fact]
    public void CompetingMotionConsistentFragmentsAreNotJoined()
    {
        PoseFrame[] frames=[Moving(0,100),Moving(.04,125),Moving(.08,150),
            new(.16,[]){Shaft=new(2,null,[new(100,190,200,190),new(100,210,200,210)],.9,false,0,0)}];
        var samples=new ShaftTrajectoryProvider().Extract(frames,0,Joint.LeftWrist);
        Assert.NotEqual(samples[^2].ContinuityId,samples[^1].ContinuityId);
    }

    private static PoseFrame Frame(double time,int track,int? owner,ShaftSegment line,double confidence=.9) =>
        new(time,[]){Shaft=new(track,owner,[line],confidence,false,0,0)};

    [Fact]
    public void OcclusionSwitchesVisibleSideWithoutInventingCentroidMovement()
    {
        var frames=new[]{
            Frame(0,1,2,new(100,200,150,205)),
            Frame(.033,2,2,new(170,211,220,216)),
            Frame(.066,2,2,new(170,214,220,219))};
        var samples=new ShaftTrajectoryProvider().Extract(frames,2,Joint.LeftWrist);
        Assert.Single(samples.Select(s=>s.ContinuityId).Distinct());
        Assert.Equal(4,samples[1].Position.Y-samples[0].Position.Y,6);
        Assert.Equal(3,samples[2].Position.Y-samples[1].Position.Y,6);
        Assert.Equal(AnalysisQuality.Reduced,samples[1].Quality);
    }

    [Theory]
    [InlineData(2,3,170,202,220,202,.033)] // Another athlete.
    [InlineData(2,null,170,202,220,202,.033)] // Unknown bar reacquired elsewhere.
    [InlineData(1,2,170,250,220,250,.033)] // Vertical jump.
    [InlineData(1,2,370,202,420,202,.033)] // Distant fragment.
    [InlineData(1,2,170,202,220,222,.033)] // Inconsistent angle.
    [InlineData(1,2,170,202,220,202,.5)] // Long disappearance.
    public void AmbiguousOrImplausibleTransitionStartsNewSegment(int track,int? owner,
        double x1,double y1,double x2,double y2,double time)
    {
        var frames=new[]{Frame(0,1,2,new(100,200,150,200)),Frame(time,track,owner,new(x1,y1,x2,y2))};
        var samples=new ShaftTrajectoryProvider().Extract(frames,0,Joint.LeftWrist);
        Assert.NotEqual(samples[0].ContinuityId,samples[1].ContinuityId);
    }

    [Fact]
    public void DoesNotChainUncertainFragmentChangesIndefinitely()
    {
        var frames=Enumerable.Range(0,4).Select(i=>Frame(i*.033,1,2,
            i%2==0?new(100,200+i,150,200+i):new(170,200+i,220,200+i))).ToArray();
        var samples=new ShaftTrajectoryProvider().Extract(frames,0,Joint.LeftWrist);
        Assert.Equal(samples[0].ContinuityId,samples[2].ContinuityId);
        Assert.NotEqual(samples[2].ContinuityId,samples[3].ContinuityId);
    }

    [Fact]
    public void LowConfidenceOrTrackOwnedByAnotherAthleteIsNotASelectedAthleteMeasurement()
    {
        var frames=new[]{
            Frame(0,1,2,new(100,200,150,200)),
            Frame(.033,2,3,new(100,201,150,201)),
            Frame(.066,1,2,new(100,202,150,202),.2),
            Frame(.1,1,2,new(100,203,150,203))};
        var samples=new ShaftTrajectoryProvider().Extract(frames,2,Joint.LeftWrist);
        Assert.Equal(new[]{0,3},samples.Select(s=>s.FrameIndex));
    }
}
