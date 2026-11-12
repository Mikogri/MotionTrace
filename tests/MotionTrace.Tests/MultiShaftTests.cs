using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.Motion;
using MotionTrace.Infrastructure.AI;

namespace MotionTrace.Tests;

public class MultiShaftTests
{
    private static ShaftDto Shaft(int track, int? owner) => new(track,owner,[new(10,50,200,50)],.9,true,-2,.04);
    private static AnalysisDto Data(params ShaftDto[] shafts) => new(2,new("test.mp4",1,720,1280,25),new("engine","pose","shaft"),
        [new(1,false),new(2,true)],[new(0,[],null,shafts)],[]);

    [Fact] public void MultipleOwnersAndParticipationSurviveTransport()
    {
        var result=AnalysisJson.Map(Data(Shaft(10,1),Shaft(20,2)));
        Assert.False(result.Athletes[0].IsExerciseParticipant);
        Assert.True(result.Athletes[1].IsExerciseParticipant);
        Assert.Equal(2,result.Frames[0].GetShafts().Count());
        Assert.Equal(20,result.Frames[0].ShaftForAthlete(2)!.TrackId);
        Assert.Null(result.Frames[0].Shaft);
    }

    [Fact] public async Task SchemaThreeMultiShaftJsonIsAccepted()
    {
        const string json="""
        {"schemaVersion":3,"video":{"fileName":"test.mp4","durationSeconds":1,"width":720,"height":1280,"framesPerSecond":25},
         "versions":{"engineVersion":"test","poseModelVersion":"pose","barbellModelVersion":"shaft"},
         "athletes":[{"id":1,"isExerciseParticipant":true},{"id":2,"isExerciseParticipant":false}],
         "frames":[{"timestampSeconds":0,"athletes":[],"shaft":null,"shafts":[
           {"trackId":1,"athleteId":1,"segments":[{"x1":10,"y1":50,"x2":200,"y2":50}],
            "confidence":0.9,"motionReliable":false,"deltaY":0,"deltaSeconds":0}]}],"limitations":[]}
        """;
        using var stream=new MemoryStream(System.Text.Encoding.UTF8.GetBytes(json));
        var result=await AnalysisJson.ReadAsync(stream);
        Assert.Equal(3,result.AnalysisSchemaVersion);
        Assert.Equal(1,Assert.Single(result.Frames[0].GetShafts()).AthleteId);
        Assert.False(result.Athletes[1].IsExerciseParticipant);
    }

    [Fact] public void LegacyParticipantDefaultsToTrue() => Assert.True(new AthleteDto(1).IsExerciseParticipant);

    [Theory]
    [InlineData(10,2)] // Duplicate track.
    [InlineData(20,1)] // Duplicate owner.
    [InlineData(20,3)] // Unknown owner.
    public void InvalidMultiShaftAssociationsAreRejected(int track,int owner) =>
        Assert.Throws<InvalidDataException>(()=>AnalysisJson.Map(Data(Shaft(10,1),Shaft(track,owner))));

    [Fact] public void AmbiguousLegacyAndNewRepresentationIsRejected()
    {
        var data=Data(Shaft(10,1));
        Assert.Throws<InvalidDataException>(()=>AnalysisJson.Map(data with {Frames=[data.Frames[0] with {Shaft=Shaft(20,2)}]}));
    }

    [Fact] public void NullAndMalformedShaftEntriesAreRejected()
    {
        Assert.Throws<InvalidDataException>(()=>AnalysisJson.Map(Data(new ShaftDto[]{null!})));
        Assert.Throws<InvalidDataException>(()=>AnalysisJson.Map(Data(Shaft(10,1) with {Segments=[new(0,0,9000,0)]})));
    }

    [Fact] public void BackgroundShaftCannotMoveSelectedAthleteReferencePosition()
    {
        var owned=new ShaftObservation(1,2,[new(50,100,150,110)],.9,false,0,0);
        var background=new ShaftObservation(2,null,[new(500,400,700,400)],.9,false,0,0);
        PoseFrame[] clean=[new(0,[]){Shafts=[owned]}];
        PoseFrame[] cluttered=[new(0,[]){Shafts=[background,owned]}];
        var provider=new ShaftTrajectoryProvider();
        Assert.Equal(provider.Extract(clean,2,Joint.LeftWrist),provider.Extract(cluttered,2,Joint.LeftWrist));
    }

    [Fact] public void MeasurementsAndExportStayWithSelectedOwner()
    {
        var result=AnalysisJson.Map(Data(Shaft(10,1),Shaft(20,2),Shaft(30,null)));
        var frames=Enumerable.Range(0,5).Select(i=>result.Frames[0] with {
            TimestampSeconds=i*.04,
            Shafts=result.Frames[0].GetShafts().Select(s=>s with {
                Segments=[new(10,50+i*(s.AthleteId==2?-2:3),200,50+i*(s.AthleteId==2?-2:3))]
            }).ToArray()
        }).ToArray();
        var samples=new ShaftTrajectoryProvider().Extract(frames,2,Joint.LeftWrist);
        Assert.Equal(5,samples.Count);
        Assert.Equal(-8,samples[^1].Position.Y-samples[0].Position.Y,6);
        Assert.Empty(new ShaftTrajectoryProvider().Extract(frames,99,Joint.LeftWrist));
        var filtered=AnalysisSelection.Filter(result,new HashSet<int>{2});
        Assert.Equal(20,Assert.Single(filtered.Frames[0].GetShafts()).TrackId);
        Assert.Equal(3,result.Frames[0].GetShafts().Count());
    }
}
