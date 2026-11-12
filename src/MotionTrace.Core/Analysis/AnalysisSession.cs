using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;

namespace MotionTrace.Core.Analysis;

public enum ProviderStatus { NotAnalyzed, NotInstalled, Queued, Running, Preparing, Ready, Failed, Cancelled, Stale }
public enum MovementSource { Barbell, LeftWrist, RightWrist }
public readonly record struct MovementKey(int AthleteId, ExerciseType Exercise, MovementSource Source, double Threshold);
public sealed record PreparedChart(MotionChartMetric Metric, MotionChartAxis Axis, IReadOnlyList<MotionChartSeries> Series);
public sealed record PreparedMovement(MovementKey Key, MovementAnalysis Analysis, ExerciseStatus[] States,
    IReadOnlyList<PreparedChart> Charts);
public sealed record ProviderSnapshot(AnalysisResult Analysis, IReadOnlyList<PreparedMovement> Movements,
    IReadOnlyDictionary<int, ExerciseClassification> Exercises)
{
    public PreparedMovement? FindMovement(MovementKey key) => Movements.FirstOrDefault(m => m.Key == key);
}
public sealed record ProviderResult(string ProviderId, ProviderStatus Status, ProviderSnapshot? Snapshot = null,
    string? ResultPath = null, string? Error = null);

/// <summary>Selection changes references only. Model and metric computation belong to the session engine.</summary>
public sealed class AnalysisSession(string sessionId, string videoPath, string targetJson)
{
    private readonly object gate = new();
    public static IReadOnlyList<string> ProviderIds { get; } = Array.AsReadOnly(new[]
        { "grounding_dino_sam2", "samurai", "tapnextpp", "bootstapir" });
    private readonly Dictionary<string, ProviderResult> results = ProviderIds.ToDictionary(id => id,
        id => new ProviderResult(id, ProviderStatus.NotAnalyzed), StringComparer.Ordinal);
    public string SessionId { get; } = sessionId;
    public string VideoPath { get; } = videoPath;
    public string TargetJson { get; private set; } = targetJson;
    public void SetResolvedTarget(string resolvedTargetJson)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(resolvedTargetJson);
        lock (gate) TargetJson = resolvedTargetJson;
    }
    public string ActiveProviderId { get; private set; } = ProviderIds[0];
    public IReadOnlyDictionary<string, ProviderResult> Providers { get { lock (gate) return results.ToDictionary(); } }
    public ProviderResult ActiveResult { get { lock (gate) return results[ActiveProviderId]; } }
    public void Update(ProviderResult result)
    {
        lock (gate)
        {
            if (!results.ContainsKey(result.ProviderId)) throw new ArgumentException("Unknown comparison provider.");
            if (result.Status == ProviderStatus.Ready && result.Snapshot is null)
                throw new ArgumentException("Ready requires a prepared snapshot.");
            if (result.Snapshot is {} snapshot && snapshot.Analysis.Versions.BarbellProvider != result.ProviderId)
                throw new ArgumentException("Snapshot belongs to a different provider.");
            results[result.ProviderId] = result;
        }
    }
    public ProviderResult Activate(string providerId)
    {
        lock (gate)
        {
            if (!results.ContainsKey(providerId)) throw new ArgumentException("Unknown comparison provider.");
            ActiveProviderId = providerId;
            return results[providerId];
        }
    }
    public void QueueAll()
    {
        lock (gate)
        {
            foreach (string id in ProviderIds) if (results[id].Status != ProviderStatus.Ready)
                results[id] = new(id, ProviderStatus.Queued);
        }
    }
    public void CancelPending()
    {
        lock (gate)
        {
            foreach (string id in ProviderIds)
                if (results[id].Status is ProviderStatus.Queued or ProviderStatus.Running or ProviderStatus.Preparing)
                    results[id] = new(id, ProviderStatus.Cancelled);
        }
    }
    public static MovementRep? MatchRepAt(ProviderSnapshot snapshot, MovementKey key, double timestamp)
    {
        var matches = snapshot.FindMovement(key)?.Analysis.Reps.Where(r => timestamp >= r.Start && timestamp <= r.End).Take(2).ToArray();
        return matches?.Length == 1 ? matches[0] : null;
    }
}

public static class ProviderPreparation
{
    public const string Version = "comparison-metrics-1";
    public static ProviderSnapshot Prepare(AnalysisResult result, string videoPath, double threshold = 1.5,
        CancellationToken token = default)
    {
        var movements = new List<PreparedMovement>();
        var exercises = new Dictionary<int, ExerciseClassification>();
        foreach (var athlete in result.Athletes)
        {
            token.ThrowIfCancellationRequested();
            // Comparison providers share one exercise decision. Provider-specific motion must not
            // silently select different rep rules when the common classifier abstains.
            var prediction = result.ExercisePredictions.FirstOrDefault(p => p.AthleteId == athlete.Id);
            exercises[athlete.Id] = prediction is null
                ? new(ExerciseType.Unknown, 0, "Shared exercise classification is unavailable; choose the exercise explicitly.")
                : new(prediction.Exercise, prediction.Score, prediction.Method);
            foreach (var source in Enum.GetValues<MovementSource>())
            {
                var joint = source == MovementSource.RightWrist ? Joint.RightWrist : Joint.LeftWrist;
                var provider = source == MovementSource.Barbell ? MeasurementSources.Barbell(result) : new WristTrajectoryProvider();
                var samples = provider.Extract(result.Frames, athlete.Id, joint, token);
                foreach (var exercise in new[] { ExerciseType.BenchPress, ExerciseType.Squat, ExerciseType.Deadlift })
                {
                    var analysis = MovementAnalyzer.AnalyzeTrajectory(samples, exercise, result.Video.Height, threshold, token);
                    if (source == MovementSource.Barbell)
                        analysis = analysis with { MeasurementSource = MeasurementSources.BarbellLabel(result, athlete.Id),
                            Note = $"{analysis.Reps.Count} complete reps · image-space px / px/s; inspect tracking quality." };
                    else if (exercise == ExerciseType.BenchPress && result.Versions.BarbellModelVersion != "unavailable")
                        analysis = ShaftRepGate.Apply(analysis, result.Frames, athlete.Id, result.Video.Height, token);
                    var key = new MovementKey(athlete.Id, exercise, source, threshold);
                    movements.Add(PreparePresentation(key, analysis, result.Video.DurationSeconds, result.Video.Height, videoPath, token));
                }
            }
        }
        return new(result, movements, exercises);
    }
    public static PreparedMovement PreparePresentation(MovementKey key, MovementAnalysis analysis, double duration,
        int height, string videoPath, CancellationToken token = default)
    {
        var selected = analysis.Reps.Select(r => r.Number).ToHashSet();
        var charts = (from metric in Enum.GetValues<MotionChartMetric>() from axis in Enum.GetValues<MotionChartAxis>()
            select new PreparedChart(metric, axis, RepChartData.Create(videoPath, analysis, selected, metric, axis))).ToArray();
        return new(key, analysis, MovementStatusTimeline.Build(analysis.Points, duration, height * .003, token), charts);
    }
}
