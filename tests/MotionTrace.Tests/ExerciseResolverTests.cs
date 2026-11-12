using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;

namespace MotionTrace.Tests;

public class ExerciseResolverTests
{
    [Theory]
    [InlineData(ExerciseType.BenchPress)]
    [InlineData(ExerciseType.Squat)]
    [InlineData(ExerciseType.Deadlift)]
    public void AssignedMovingBarAndAnatomyRecoverUnknown(ExerciseType exercise) =>
        Assert.Equal(exercise, ExerciseResolver.Resolve(Recording(exercise), 1).ExerciseType);

    [Fact] public void StationaryBarDoesNotTurnSetupIntoExercise() =>
        Assert.Equal(ExerciseType.Unknown, ExerciseResolver.Resolve(Recording(ExerciseType.BenchPress, stationary: true), 1).ExerciseType);

    [Fact] public void UnassignedBarDoesNotConfirmMovingPerson() =>
        Assert.Equal(ExerciseType.Unknown, ExerciseResolver.Resolve(Recording(ExerciseType.Squat, assigned: false), 1).ExerciseType);

    [Fact] public void SpotterIsNotClassified() =>
        Assert.Equal(ExerciseType.Unknown, ExerciseResolver.Resolve(Recording(ExerciseType.Deadlift) with
        { Athletes = [new(1, "Spotter") { IsExerciseParticipant = false }] }, 1).ExerciseType);

    [Fact] public void AcceptedModelDecisionIsPreserved()
    {
        var recording = Recording(ExerciseType.Squat) with
        { ExercisePredictions = [new(1, ExerciseType.BenchPress, .8, .3, [], "xclip")] };
        Assert.Equal(ExerciseType.BenchPress, ExerciseResolver.Resolve(recording, 1).ExerciseType);
    }

    [Theory]
    [InlineData(ExerciseType.Snatch)]
    [InlineData(ExerciseType.CleanAndJerk)]
    public void KnownOlympicExerciseCannotBeOverriddenByDeadliftFallback(ExerciseType exercise)
    {
        var recording = Recording(ExerciseType.Deadlift) with
        { ExercisePredictions = [new(1, exercise, .8, .3, [], "xclip")] };
        Assert.Equal(exercise, ExerciseResolver.Resolve(recording, 1).ExerciseType);
    }

    [Fact] public void InitialBenchUnrackDoesNotConfirmRep() =>
        Assert.Equal(ExerciseType.Unknown, ExerciseResolver.Resolve(Recording(ExerciseType.BenchPress, unrackOnly: true), 1).ExerciseType);

    [Fact] public void MaskProxyOffsetIsNotTreatedAsActualShaftHeight()
    {
        var input = Recording(ExerciseType.Deadlift);
        input = input with { Frames = input.Frames.Select(f => f with { Objects = f.Objects.Select(o => o with
        { Measurement = o.Measurement! with { Position = new(200, o.Measurement!.Position.Y + 300), IsProxy = true } }).ToArray() }).ToArray() };
        Assert.Equal(ExerciseType.Deadlift, ExerciseResolver.Resolve(input, 1).ExerciseType);
    }

    [Fact] public void MovingUnrelatedBarDoesNotClassifyStationaryAthlete()
    {
        var input = Recording(ExerciseType.Squat);
        input = input with { Frames = input.Frames.Select(f => f with { Athletes = input.Frames[0].Athletes }).ToArray() };
        Assert.Equal(ExerciseType.Unknown, ExerciseResolver.Resolve(input, 1).ExerciseType);
    }

    [Fact] public void ConflictingMovementsRemainUnknown()
    {
        var squat = Recording(ExerciseType.Squat);
        var deadlift = Recording(ExerciseType.Deadlift);
        var input = squat with { Frames = squat.Frames.Concat(deadlift.Frames.Select(f => f with { TimestampSeconds = f.TimestampSeconds + 6 })).ToArray() };
        Assert.Equal(ExerciseType.Unknown, ExerciseResolver.Resolve(input, 1).ExerciseType);
    }

    private static AnalysisResult Recording(ExerciseType exercise, bool stationary = false, bool assigned = true, bool unrackOnly = false)
    {
        var frames = new List<PoseFrame>();
        for (int i = 0; i <= 150; i++)
        {
            double t = i / 30.0;
            double offset = t < 1 ? 0 : t < 2 ? (t - 1) * 100 : t < 3 ? 100 : t < 4 ? (4 - t) * 100 : 0;
            if (unrackOnly) offset = t < 1 ? 100 : t < 2 ? (2 - t) * 100 : 0;
            double y = exercise == ExerciseType.Deadlift ? 600 - offset : 300 + offset;
            Point2 shoulder = exercise == ExerciseType.BenchPress ? new(200, 470) : exercise == ExerciseType.Squat ? new(200, y) : new(200, y - 220);
            Point2 hip = exercise == ExerciseType.BenchPress ? new(400, 470) : new(200, shoulder.Y + 200);
            var pose = new AthletePose(1, new(0, 0, 700, 900), .95,
                [new(Joint.LeftShoulder, shoulder, .95), new(Joint.LeftHip, hip, .95), new(Joint.LeftWrist, new(200, y), .95)]);
            frames.Add(new(t, [pose]) { Objects = [new("bar", assigned ? 1 : null, null, null, .95, TrackingState.Tracked,
                new(new(200, stationary ? 300 : y), "test", AnalysisQuality.Good, false, false, false))] });
        }
        return new(4, new("no-exercise-hint.mp4", 5, 1000, 1000, 30), new("test", "test", "test"), [new(1, "Person")], frames, []);
    }
}
