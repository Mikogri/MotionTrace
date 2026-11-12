using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;

namespace MotionTrace.Core.Analysis;

public sealed record VideoMetadata(string FileName, double DurationSeconds, int Width, int Height, double FramesPerSecond);
public sealed record EngineVersions(string EngineVersion, string PoseModelVersion, string BarbellModelVersion)
{
    public string PoseModel { get; init; } = "unspecified";
    public string TrackerVersion { get; init; } = "legacy";
    public string CorrectionVersion { get; init; } = "none";
    public string? BarbellProvider { get; init; }
    public string? MeasurementVersion { get; init; }
}
public sealed record AnalysisResult(int AnalysisSchemaVersion, VideoMetadata Video, EngineVersions Versions,
    IReadOnlyList<AthleteTrack> Athletes, IReadOnlyList<PoseFrame> Frames, IReadOnlyList<string> Limitations)
{
    public IReadOnlyList<ExercisePrediction> ExercisePredictions { get; init; } = [];
    public string? VisionMetadataJson { get; init; }
    public string? VideoHash { get; init; }
}
public sealed record ExerciseWindow(double StartSeconds, double EndSeconds,
    IReadOnlyDictionary<string, double> Scores, ExerciseType Decision)
{
    public IReadOnlyList<double> PromptLogits { get; init; } = [];
    public IReadOnlyList<double?> SampleTimestamps { get; init; } = [];
    public double Score { get; init; }
    public double Margin { get; init; }
    public string? Reason { get; init; }
}
public sealed record ExercisePrediction(int AthleteId, ExerciseType Exercise, double Score, double Margin,
    IReadOnlyList<ExerciseWindow> Windows, string Method)
{
    public string? Aggregation { get; init; }
    public string? ScoreMeaning { get; init; }
    public ExerciseType? ModelExercise { get; init; }
    public string? OwnershipGate { get; init; }
}
public sealed record AnalysisProgress(string Stage, double? Fraction = null);

public interface IPoseAnalysisEngine
{
    Task<AnalysisResult> AnalyzeAsync(string videoPath, IProgress<AnalysisProgress> progress, CancellationToken cancellationToken);
}

public static class FrameLookup
{
    /// <summary>Never show a future pose or carry an old pose through a detection gap.</summary>
    public static PoseFrame? At(IReadOnlyList<PoseFrame> frames, double time, double maximumAge = 0.15)
    {
        int low = 0, high = frames.Count - 1, found = -1;
        while (low <= high)
        {
            int mid = low + (high - low) / 2;
            if (frames[mid].TimestampSeconds <= time) { found = mid; low = mid + 1; }
            else high = mid - 1;
        }
        return found >= 0 && time - frames[found].TimestampSeconds <= maximumAge ? frames[found] : null;
    }
}
