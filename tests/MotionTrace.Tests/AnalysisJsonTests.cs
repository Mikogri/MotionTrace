using System.Text;
using System.Text.Json;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using MotionTrace.Infrastructure.AI;

namespace MotionTrace.Tests;

public class AnalysisJsonTests
{
    private const string ValidJson = """
    {"schemaVersion":1,"video":{"fileName":"test.mp4","durationSeconds":1,"width":720,"height":1280,"framesPerSecond":30},
     "versions":{"engineVersion":"0.1","poseModelVersion":"rtmpose:test","barbellModelVersion":"unavailable"},
     "athletes":[{"id":7}],"frames":[{"timestampSeconds":0,"athletes":[{"athleteId":7,"confidence":0.9,
     "boundingBox":{"x":10,"y":20,"width":100,"height":200},"keypoints":[{"joint":"LeftKnee","x":42,"y":81,"confidence":0.8}]}]}],"limitations":[]}
    """;
    private static Task<AnalysisResult> Parse(string json) => AnalysisJson.ReadAsync(new MemoryStream(Encoding.UTF8.GetBytes(json)));
    [Fact] public async Task JsonMapsSemanticJointsAndTrackIds()
    {
        var analysis = await Parse(ValidJson);
        Assert.Equal(7, analysis.Athletes[0].Id);
        Assert.Equal(Joint.LeftKnee, analysis.Frames[0].Athletes[0].Keypoints[0].Joint);
        Assert.Equal(42, analysis.Frames[0].Athletes[0].Keypoints[0].Position.X);
    }
    [Fact] public async Task UnsupportedSchemaIsRejected() => await Assert.ThrowsAsync<InvalidDataException>(() => Parse(ValidJson.Replace("\"schemaVersion\":1", "\"schemaVersion\":99")));
    [Fact] public async Task SchemaTwoPreservesTrackingMetadata()
    {
        var json=ValidJson.Replace("\"schemaVersion\":1","\"schemaVersion\":2").Replace("\"athleteId\":7,","\"athleteId\":7,\"trackingState\":\"Lost\",\"occlusionRisk\":\"High\",\"trackingConfidence\":0,");
        var result=await Parse(json);var pose=result.Frames[0].Athletes[0];
        Assert.Equal(TrackingState.Lost,pose.TrackingState);Assert.Equal(OcclusionRisk.High,pose.OcclusionRisk);Assert.Equal(0,pose.TrackingConfidence);
    }
    [Fact] public async Task UnknownAthleteIsRejected() => await Assert.ThrowsAsync<InvalidDataException>(() => Parse(ValidJson.Replace("\"athleteId\":7", "\"athleteId\":8")));
    [Fact] public async Task ShaftCoordinatesAndMotionSurviveTransport()
    {
        var json=ValidJson.Replace("\"timestampSeconds\":0", "\"shaft\":{\"trackId\":1,\"athleteId\":7,\"segments\":[{\"x1\":10,\"y1\":50,\"x2\":200,\"y2\":60}],\"confidence\":0.9,\"motionReliable\":false,\"deltaY\":0,\"deltaSeconds\":0},\"timestampSeconds\":0");
        var shaft=(await Parse(json)).Frames[0].Shaft;
        Assert.NotNull(shaft);Assert.Equal(7,shaft.AthleteId);Assert.Equal(200,Assert.Single(shaft.Segments).X2);
        await Assert.ThrowsAsync<InvalidDataException>(()=>Parse(json.Replace("\"x2\":200","\"x2\":9000")));
    }
    [Fact] public async Task MalformedJsonIsRejected() => await Assert.ThrowsAsync<JsonException>(() => Parse("{broken"));
    [Fact] public async Task MissingMetadataIsRejected() => await Assert.ThrowsAsync<InvalidDataException>(() => Parse("{\"schemaVersion\":1}"));
    [Fact] public async Task InvalidConfidenceIsRejected() => await Assert.ThrowsAsync<InvalidDataException>(() => Parse(ValidJson.Replace("\"confidence\":0.8", "\"confidence\":3")));
    [Fact] public async Task ParsingHonorsCancellation()
    {
        using var source = new CancellationTokenSource(); source.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => AnalysisJson.ReadAsync(new MemoryStream(Encoding.UTF8.GetBytes(ValidJson)), source.Token));
    }
    [Fact] public void FrameLookupDoesNotShowFutureOrStalePose()
    {
        PoseFrame[] frames = [new(1, []), new(2, [])];
        Assert.Null(FrameLookup.At(frames, 0.9));
        Assert.Same(frames[0], FrameLookup.At(frames, 1.01));
        Assert.Null(FrameLookup.At(frames, 1.9));
        Assert.Same(frames[1], FrameLookup.At(frames, 2));
    }
}
