using MotionTrace.Core.Athletes;
using MotionTrace.Core.Motion;
using MotionTrace.Infrastructure.AI;

namespace MotionTrace.Tests;

public sealed class TwoPointTrajectoryTests
{
    private static TrackedObject Point(int index, double y, bool visible = true) =>
        new($"bar-{index}", 1, null, null, .9, visible ? TrackingState.Tracked : TrackingState.Lost,
            visible ? new(new(20 + index * 40, y), "tapnextpp", AnalysisQuality.Reduced, false, false, false) : null)
        { MeasurementGroupId = "bar", PointIndex = index };

    [Fact]
    public void PairUsesMidpointAndNeverSubstitutesTheRemainingPoint()
    {
        PoseFrame[] frames = [
            new(0, []) { Objects = [Point(0, 20), Point(1, 40)] },
            new(.03, []) { Objects = [Point(0, 30), Point(1, 80, false)] },
            new(.06, []) { Objects = [Point(0, 40), Point(1, 60)] }];
        var samples = new ObjectTrajectoryProvider().Extract(frames, 1, Joint.LeftWrist);
        Assert.Equal(2, samples.Count);
        Assert.Equal(new Point2(40, 30), samples[0].Position);
        Assert.Equal(new Point2(40, 50), samples[1].Position);
        Assert.NotEqual(samples[0].ContinuityId, samples[1].ContinuityId);
        Assert.All(samples, sample => Assert.Equal("tapnextpp-midpoint", sample.Source));
    }

    [Fact]
    public void UnrelatedObjectsAndDuplicatePointIndicesAreNotAveraged()
    {
        foreach (var objects in new[] {
            new[] { Point(0, 20), Point(1, 40) with { MeasurementGroupId = "other" } },
            new[] { Point(0, 20), Point(0, 40) with { ObjectId = "duplicate" } },
            new[] { Point(0, 20) } })
            Assert.Empty(new ObjectTrajectoryProvider().Extract([new(0, []) { Objects = objects }], 1, Joint.LeftWrist));
    }


    [Fact]
    public void PairedPointJitterDoesNotProduceMotionOrChangeRawObservations()
    {
        var samples = Enumerable.Range(0, 181).Select(i => {
            double time = i / 30.0, y = 100 + .4 * Math.Sin(time * 8);
            return new MotionSample(i, time, new(50, y), new(50, y), .95, AnalysisQuality.Good)
                { Source = "tapnextpp-midpoint" };
        }).ToArray();
        var analysis = MovementAnalyzer.AnalyzeTrajectory(samples, MotionTrace.Core.Exercise.ExerciseType.BenchPress, 1000);
        Assert.Empty(analysis.Reps);
        Assert.All(analysis.Points, point => Assert.InRange(Math.Abs(point.Velocity), 0, 1e-10));
        Assert.True(analysis.Points.Max(p => p.RawY) - analysis.Points.Min(p => p.RawY) > .7);
    }

    [Theory]
    [InlineData(MotionTrace.Core.Exercise.ExerciseType.BenchPress)]
    [InlineData(MotionTrace.Core.Exercise.ExerciseType.Squat)]
    public void PairedPointNoisePreservesFourPhases(MotionTrace.Core.Exercise.ExerciseType exercise)
    {
        var samples = Enumerable.Range(0, 211).Select(i => {
            double time = i / 30.0;
            double y = time < .6 ? 112 - time * 20 : time < 2 ? 100 : time < 3 ? 100 + (time - 2) * 80 :
                time < 4 ? 180 : time < 5 ? 180 - (time - 4) * 80 : 100;
            y += .2 * Math.Sin(time * 8);
            return new MotionSample(i, time, new(50, y), new(50, y), .95, AnalysisQuality.Good)
                { Source = "tapnextpp-midpoint" };
        }).ToArray();
        var frames = samples.Select(s => new PoseFrame(s.TimestampSeconds, []) {
            Objects = [Point(0, s.Position.Y - 20), Point(1, s.Position.Y + 20)]
        }).ToArray();
        var paired = new ObjectTrajectoryProvider().Extract(frames, 1, Joint.LeftWrist);
        var rep = Assert.Single(MovementAnalyzer.AnalyzeTrajectory(paired, exercise, 1000).Reps);
        Assert.InRange(rep.Start, 1.85, 2.15);
        Assert.InRange(rep.Lowering!.Duration, .8, 1.2);
        Assert.InRange(rep.PauseSeconds, .8, 1.2);
        Assert.InRange(rep.Lifting.Duration, .8, 1.2);
        Assert.True(rep.PreparationSeconds > 0);
    }

    [Fact]
    public void SmallPerFrameDisplacementStillAccumulatesIntoRealSlowMovement()
    {
        var samples = Enumerable.Range(0, 301).Select(i => new MotionSample(i, i / 30.0,
            new(50, 100 + i * .1), new(50, 100 + i * .1), .95, AnalysisQuality.Good)
            { Source = "tapnextpp-midpoint" }).ToArray();
        var analysis = MovementAnalyzer.AnalyzeTrajectory(samples, MotionTrace.Core.Exercise.ExerciseType.Deadlift, 1000);
        Assert.InRange(analysis.Points[^1].Y - analysis.Points[0].Y, 28, 30);
        Assert.All(analysis.Points, point => Assert.InRange(Math.Abs(point.Y - point.RawY), 0, 1.2));
    }

    [Fact]
    public void PairedDeadliftStartsWithPullAndDoesNotRequireInitialLowering()
    {
        var frames = Enumerable.Range(0, 181).Select(i => {
            double time = i / 30.0;
            double y = time < 2 ? 180 : time < 3 ? 180 - (time - 2) * 80 :
                time < 4 ? 100 : time < 5 ? 100 + (time - 4) * 80 : 180;
            y += .2 * Math.Sin(time * 8);
            return new PoseFrame(time, []) { Objects = [Point(0, y - 20), Point(1, y + 20)] };
        }).ToArray();
        var samples = new ObjectTrajectoryProvider().Extract(frames, 1, Joint.LeftWrist);
        var rep = Assert.Single(MovementAnalyzer.AnalyzeTrajectory(samples,
            MotionTrace.Core.Exercise.ExerciseType.Deadlift, 1000).Reps);
        Assert.InRange(rep.Lifting.Start, 1.85, 2.15);
        Assert.InRange(rep.Lifting.Duration, .8, 1.2);
        Assert.True(rep.LoweringFollowsLifting);
        Assert.InRange(rep.PauseSeconds, .8, 1.2);
    }

    [Fact]
    public async Task PairIdentityAndRawVisibilitySurviveJsonRoundTrip()
    {
        const string json = """
        {"schemaVersion":4,"video":{"fileName":"clip.mp4","durationSeconds":1,"width":100,"height":100,"framesPerSecond":30},
        "versions":{"engineVersion":"test","poseModelVersion":"test","barbellModelVersion":"tapnextpp"},
        "athletes":[{"id":1}],"limitations":[],"frames":[{"timestampSeconds":0,"athletes":[],"objects":[
        {"objectId":"bar-0","athleteId":1,"confidence":0.9,"trackingState":"Tracked","measurementGroupId":"bar","pointIndex":0,
         "measurement":{"x":20,"y":30,"source":"tapnextpp","quality":"Reduced"},"rawObservation":{"x":20,"y":30,"visible":true,"visibilityProbability":0.9}},
        {"objectId":"bar-1","athleteId":1,"confidence":0.1,"trackingState":"Lost","measurementGroupId":"bar","pointIndex":1,
         "rawObservation":{"x":45,"y":40,"visible":false,"visibilityProbability":0.1}}
        ]}]}
        """;
        using var input = new MemoryStream(System.Text.Encoding.UTF8.GetBytes(json));
        var result = await AnalysisJson.ReadAsync(input);
        using var output = new MemoryStream();
        await AnalysisJson.WriteAsync(output, result);
        output.Position = 0;
        var restored = await AnalysisJson.ReadAsync(output);
        Assert.Equal("bar", restored.Frames[0].Objects[0].MeasurementGroupId);
        Assert.Equal(1, restored.Frames[0].Objects[1].PointIndex);
        Assert.Contains("false", restored.Frames[0].Objects[1].RawObservationJson);
        Assert.Empty(new ObjectTrajectoryProvider().Extract(restored.Frames, 1, Joint.LeftWrist));
        using var csv = new StringWriter(System.Globalization.CultureInfo.InvariantCulture);
        TrackingPointCsv.Write(csv, restored);
        Assert.Contains("0,0,1,1,\"bar-1\",False,45,40,", csv.ToString());
        var invisible = csv.ToString().Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries)[^1].Split(',');
        Assert.Equal(.1, double.Parse(invisible[8], System.Globalization.CultureInfo.InvariantCulture));
        Assert.Equal(new[] { "False", "", "" }, invisible[9..]);
    }
}
