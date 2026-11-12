using MotionTrace.Core.Athletes;

namespace MotionTrace.Core.Exercise;

public enum ExerciseType { Unknown, Squat, BenchPress, Deadlift, Snatch, CleanAndJerk }
public enum ExerciseStatus { Waiting, Performing, Finished }
public enum RepPhase { Eccentric, Pause, Concentric }
public sealed record ExerciseClassification(ExerciseType ExerciseType, double Confidence, string Limitation);
public interface IExerciseClassifier
{
    ExerciseClassification Classify(IReadOnlyList<PoseFrame> frames, int athleteId);
}

// A camera-angle-validated classifier is intentionally not claimed by the pose-only vertical slice.
public sealed class UnavailableExerciseClassifier : IExerciseClassifier
{
    public ExerciseClassification Classify(IReadOnlyList<PoseFrame> frames, int athleteId) =>
        new(ExerciseType.Unknown, 0, "Exercise classifier has not been validated for this camera view.");
}

/// <summary>Consumes a movement signal from a future exercise-specific analyzer, not raw frames.</summary>
public sealed class ExerciseStateMachine(double startAfterSeconds = 0.3, double finishAfterSeconds = 3)
{
    private double? lastTime, movingSince, stillSince;
    public ExerciseStatus Status { get; private set; } = ExerciseStatus.Waiting;

    public ExerciseStatus Update(double timestamp, bool moving)
    {
        if (!double.IsFinite(timestamp) || timestamp < 0 || (lastTime.HasValue && timestamp <= lastTime))
            throw new ArgumentOutOfRangeException(nameof(timestamp));
        if (startAfterSeconds < 0 || finishAfterSeconds <= 0) throw new InvalidOperationException("Invalid temporal thresholds.");
        // A missing interval is not evidence of continuous motion or rest.
        if (lastTime.HasValue && timestamp - lastTime > 0.5) { movingSince = null; stillSince = null; }
        lastTime = timestamp;
        if (moving) { stillSince = null; movingSince ??= timestamp; }
        else { movingSince = null; stillSince ??= timestamp; }
        if (Status != ExerciseStatus.Performing && movingSince.HasValue && timestamp - movingSince >= startAfterSeconds)
            Status = ExerciseStatus.Performing;
        if (Status == ExerciseStatus.Performing && stillSince.HasValue && timestamp - stillSince >= finishAfterSeconds)
            Status = ExerciseStatus.Finished;
        return Status;
    }
}

public sealed record PhaseInterval(RepPhase Phase, double StartSeconds, double EndSeconds);
public sealed class Repetition
{
    public int Number { get; }
    public double StartSeconds { get; }
    public double EndSeconds { get; }
    public double TotalSeconds => EndSeconds - StartSeconds;
    public IReadOnlyList<PhaseInterval> Phases { get; }

    public Repetition(int number, double startSeconds, double endSeconds, IEnumerable<PhaseInterval>? phases = null)
    {
        if (number < 1 || !double.IsFinite(startSeconds) || !double.IsFinite(endSeconds) || startSeconds < 0 || endSeconds <= startSeconds)
            throw new ArgumentException("A repetition needs a positive number and an ordered time interval.");
        var intervals = (phases ?? []).ToArray();
        double previousEnd = startSeconds;
        foreach (var interval in intervals)
        {
            if (!double.IsFinite(interval.StartSeconds) || !double.IsFinite(interval.EndSeconds) ||
                interval.StartSeconds < previousEnd || interval.EndSeconds <= interval.StartSeconds || interval.EndSeconds > endSeconds)
                throw new ArgumentException("Rep phases must be ordered, non-overlapping and inside the repetition.");
            previousEnd = interval.EndSeconds;
        }
        Number = number; StartSeconds = startSeconds; EndSeconds = endSeconds; Phases = intervals;
    }
}
