using System.Text;
using System.Text.Json;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;
using MotionTrace.Infrastructure.AI;

namespace MotionTrace.Tests;

public sealed class VisionIntegrationTests
{
    private const string Json = """
    {"schemaVersion":4,"video":{"fileName":"clip.mp4","durationSeconds":1,"width":100,"height":200,"framesPerSecond":30},
    "versions":{"engineVersion":"vision-1","poseModelVersion":"rtmpose","barbellModelVersion":"sam2"},
    "athletes":[{"id":1}],"frames":[{"timestampSeconds":0,"athletes":[],"shafts":[],"objects":[
    {"objectId":"bar-1","athleteId":1,"box":{"x":10,"y":20,"width":30,"height":40},"maskPath":"mask.png","confidence":0.9,
    "trackingState":"Tracked","measurement":{"x":20,"y":30,"source":"mask-proxy","quality":"Reduced","isProxy":true,"isInterpolated":false,"isManualCorrection":false}}]}],
    "exercisePredictions":[{"athleteId":1,"exercise":"Snatch","score":0.7,"margin":0.2,"method":"xclip-window-v1",
    "aggregation":"window mean","scoreMeaning":"relative prompt softmax",
    "windows":[{"startSeconds":0,"endSeconds":1,"decision":"Snatch","scores":{"Snatch":0.7,"Unknown":0.3},
    "promptLogits":[12.3,10.4],"sampleTimestamps":[0,0.1],"reason":"accepted"}]}],
    "visionMetadata":{"models":{"xclip":"revision-123"}},"limitations":[]}
    """;
    private static Task<AnalysisResult> Parse(string json) => AnalysisJson.ReadAsync(new MemoryStream(Encoding.UTF8.GetBytes(json)));

    [Fact] public async Task SchemaFourRoundTripsPredictionAndMeasurementProvenance()
    {
        var result = await Parse(Json);
        Assert.Equal(ExerciseType.Snatch, Assert.Single(result.ExercisePredictions).Exercise);
        Assert.Empty(result.Frames[0].GetShafts());
        var observed = Assert.Single(result.Frames[0].Objects);
        Assert.True(observed.Measurement!.IsProxy);
        using var stream = new MemoryStream();
        await AnalysisJson.WriteAsync(stream, result);
        stream.Position = 0;
        var loaded = await AnalysisJson.ReadAsync(stream);
        Assert.Equal(observed, Assert.Single(loaded.Frames[0].Objects));
        Assert.Contains("revision-123", loaded.VisionMetadataJson);
        Assert.Equal("window mean", loaded.ExercisePredictions[0].Aggregation);
        Assert.Equal(new[] {12.3,10.4}, loaded.ExercisePredictions[0].Windows[0].PromptLogits);
        Assert.Equal(new double?[] {0,.1}, loaded.ExercisePredictions[0].Windows[0].SampleTimestamps);
    }

    [Fact] public async Task ExportRoundTripPreservesCorrectedPoseEvidence()
    {
        var result = await Parse(Json);
        var point = new Keypoint(Joint.LeftWrist,new(20,30),.6) { RawPosition=new(21,32),ModelConfidence=.8,
            TrackingConfidence=.75,IsCorrected=true,IsInterpolated=true };
        var pose = new AthletePose(1,new(0,0,40,100),.9,[point]) { Quality=AnalysisQuality.Reduced };
        result=result with { Frames=[result.Frames[0] with {Athletes=[pose]}] };
        using var stream = new MemoryStream();
        await AnalysisJson.WriteAsync(stream,result); stream.Position=0;
        var loaded=await AnalysisJson.ReadAsync(stream);
        Assert.Equal(point,loaded.Frames[0].Athletes[0].Keypoints[0]);
        Assert.Equal(AnalysisQuality.Reduced,loaded.Frames[0].Athletes[0].Quality);
    }

    [Fact] public async Task ExportPreservesRawModelDecisionWhenOwnershipGateAbstains()
    {
        var result = await Parse(Json.Replace("\"exercise\":\"Snatch\"",
            "\"exercise\":\"Unknown\",\"modelExercise\":\"Snatch\",\"ownershipGate\":\"no-verified-object-owner\""));
        using var stream = new MemoryStream();
        await AnalysisJson.WriteAsync(stream, result);
        stream.Position = 0;
        var loaded = await AnalysisJson.ReadAsync(stream);
        var prediction = Assert.Single(loaded.ExercisePredictions);
        Assert.Equal(ExerciseType.Unknown, prediction.Exercise);
        Assert.Equal(ExerciseType.Snatch, prediction.ModelExercise);
        Assert.Equal("no-verified-object-owner", prediction.OwnershipGate);
        Assert.Equal(.7, prediction.Score);
        Assert.Equal(ExerciseType.Snatch, prediction.Windows[0].Decision);
    }

    [Fact] public async Task LostObjectAllowsNoBoxButCannotInventMeasurement()
    {
        var result = await Parse(Json.Replace("\"trackingState\":\"Tracked\"", "\"trackingState\":\"Lost\"")
            .Replace("\"box\":{\"x\":10,\"y\":20,\"width\":30,\"height\":40}", "\"box\":null")
            .Replace("\"measurement\":{\"x\":20,\"y\":30,\"source\":\"mask-proxy\",\"quality\":\"Reduced\",\"isProxy\":true,\"isInterpolated\":false,\"isManualCorrection\":false}", "\"measurement\":null"));
        Assert.Null(result.Frames[0].Objects[0].Measurement);
        Assert.Empty(new ObjectTrajectoryProvider().Extract(result.Frames, 1, Joint.LeftWrist));
        await Assert.ThrowsAsync<InvalidDataException>(() => Parse(Json.Replace("\"trackingState\":\"Tracked\"", "\"trackingState\":\"Lost\"")));
    }

    [Fact] public async Task InvalidProxyAndUnknownOwnerAreRejected()
    {
        await Assert.ThrowsAsync<InvalidDataException>(() => Parse(Json.Replace("\"isProxy\":true", "\"isProxy\":false")));
        await Assert.ThrowsAsync<InvalidDataException>(() => Parse(Json.Replace("\"athleteId\":1", "\"athleteId\":2")));
    }

    [Fact] public async Task ObjectTrajectoryNeverBridgesIdentitySourceOrLostFrames()
    {
        var result = await Parse(Json);
        var observation = result.Frames[0].Objects[0];
        PoseFrame F(double time, TrackedObject? o) => new(time, []) { Objects = o is null ? [] : [o] };
        PoseFrame[] frames = [F(0, observation), F(.03, observation), F(.06, null), F(.09, observation),
            F(.12, observation with { ObjectId = "bar-2" }), F(.15, observation with {
                ObjectId = "bar-2", Measurement = observation.Measurement! with { Source = "manual-lk", IsProxy = false } })];
        var samples = new ObjectTrajectoryProvider().Extract(frames, 1, Joint.LeftWrist);
        Assert.Equal(5, samples.Count);
        Assert.Equal(samples[0].ContinuityId, samples[1].ContinuityId);
        Assert.NotEqual(samples[1].ContinuityId, samples[2].ContinuityId);
        Assert.NotEqual(samples[2].ContinuityId, samples[3].ContinuityId);
        Assert.NotEqual(samples[3].ContinuityId, samples[4].ContinuityId);
        Assert.Empty(new ObjectTrajectoryProvider().Extract(frames, 2, Joint.LeftWrist));
    }

    [Fact] public async Task SelectionFiltersObjectsAndPredictionsWithoutLosingProvenance()
    {
        var result = await Parse(Json);
        var filtered = AnalysisSelection.Filter(result, new HashSet<int>());
        Assert.Empty(filtered.Frames[0].Objects);
        Assert.Empty(filtered.ExercisePredictions);
        Assert.Equal(result.VisionMetadataJson, filtered.VisionMetadataJson);
    }

    [Fact] public async Task MeasurementCsvPreservesProxyFlagsAndOriginalTimestamps()
    {
        var result = await Parse(Json);
        var observation = result.Frames[0].Objects[0];
        var frames = new[] { .001, .036, .081 }.Select(time => new PoseFrame(time, []) { Objects = [observation] }).ToArray();
        var samples = new ObjectTrajectoryProvider().Extract(frames, 1, Joint.LeftWrist);
        var movement = MovementAnalyzer.AnalyzeTrajectory(samples, ExerciseType.BenchPress, 200);
        Assert.Equal(frames.Select(f => f.TimestampSeconds), movement.Points.Select(p => p.Time));
        Assert.All(movement.Points, p => { Assert.True(p.IsProxy); Assert.Equal("mask-proxy", p.Source); Assert.Equal("bar-1", p.ObjectId); });
        using var csv = new StringWriter();
        MovementCsv.WriteSamples(csv, movement);
        Assert.Contains("object_id,is_proxy,is_interpolated,is_manual_correction", csv.ToString());
        Assert.Contains("\"mask-proxy\"", csv.ToString());
    }

    [Fact] public async Task PoorPointAndManualCorrectionSplitContinuityWithoutZeroFilling()
    {
        var result = await Parse(Json);
        var observation = result.Frames[0].Objects[0];
        var frames = new PoseFrame[]
        {
            new(0, []) { Objects = [observation] },
            new(.03, []) { Objects = [observation with { Measurement = observation.Measurement! with { Quality = AnalysisQuality.Poor } }] },
            new(.06, []) { Objects = [observation] },
            new(.09, []) { Objects = [observation with { Measurement = observation.Measurement! with { IsManualCorrection = true } }] }
        };
        var samples = new ObjectTrajectoryProvider().Extract(frames, 1, Joint.LeftWrist);
        Assert.Equal(new[] { 0.0, .06, .09 }, samples.Select(s => s.TimestampSeconds));
        Assert.Equal(3, samples.Select(s => s.ContinuityId).Distinct().Count());
        Assert.All(samples, s => Assert.Equal(30, s.Position.Y));
    }

    [Theory]
    [InlineData(150, 100, 300, 200, 100, 200, 50, 100)]
    [InlineData(100, 150, 200, 300, 200, 100, 100, 50)]
    public void CorrectionCoordinatesUndoLetterboxing(double x, double y, double width, double height,
        int imageWidth, int imageHeight, double expectedX, double expectedY)
    {
        var point = VideoCoordinates.FromViewport(new(x, y), width, height, imageWidth, imageHeight);
        Assert.Equal(new Point2(expectedX, expectedY), point);
        Assert.Null(VideoCoordinates.FromViewport(new(0, 0), width, height, imageWidth, imageHeight));
    }

    [Theory]
    [InlineData(90)]
    [InlineData(270)]
    [InlineData(-90)]
    public void PortraitMovCoordinatesUseDisplayRotation(int rotation)
    {
        var size = VideoCoordinates.DisplaySize(3840, 2160, rotation);
        Assert.Equal((2160, 3840), size);
        Assert.Equal(new Point2(1080, 1920), VideoCoordinates.FromViewport(new(150, 200), 300, 400, size.Width, size.Height));
        Assert.Equal((3840, 2160), VideoCoordinates.DisplaySize(3840, 2160, 180));
    }

    [Fact] public async Task ManualChoicesPersistSeparatelyAndAreScopedToVideo()
    {
        string directory = Path.Combine(Path.GetTempPath(), "MotionTrace-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            var store = new VideoCorrections(directory, new string('a', 64));
            await store.SaveExercisesAsync(new Dictionary<int, ExerciseType> { [1] = ExerciseType.Deadlift });
            await store.SaveObjectAsync(new("manual-1", 1, .3, Point: [25, 30]));
            var reloaded = new VideoCorrections(directory, new string('a', 64));
            Assert.Equal(ExerciseType.Deadlift, (await reloaded.ReadExercisesAsync())[1]);
            Assert.True(File.Exists(reloaded.ObjectPath));
            Assert.Empty(await new VideoCorrections(directory, new string('b', 64)).ReadExercisesAsync());
            using var json = JsonDocument.Parse(await File.ReadAllTextAsync(reloaded.ObjectPath));
            Assert.Equal(.3, json.RootElement.GetProperty("objects")[0].GetProperty("timestampSeconds").GetDouble());
        }
        finally { if (Directory.Exists(directory)) Directory.Delete(directory, true); }
    }

    [Fact] public async Task OlympicLiftsCannotAccidentallyUseSbdRepRules()
    {
        var result = await Parse(Json);
        var samples = new ObjectTrajectoryProvider().Extract(result.Frames, 1, Joint.LeftWrist);
        Assert.Throws<ArgumentException>(() => MovementAnalyzer.AnalyzeTrajectory(samples, ExerciseType.Snatch, 200));
        Assert.Throws<ArgumentException>(() => MovementAnalyzer.AnalyzeTrajectory(samples, ExerciseType.CleanAndJerk, 200));
        Assert.EndsWith("pipeline.py", new PythonOptions().ScriptPath);
        Assert.Equal("custom_barbell", new PythonOptions().BarbellProvider);
        Assert.True(Path.IsPathFullyQualified(new PythonOptions().ExecutablePath));
    }
}
