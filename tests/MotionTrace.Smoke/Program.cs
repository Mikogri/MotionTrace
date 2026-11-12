using System.Diagnostics;
using MotionTrace.Core.Analysis;
using MotionTrace.Infrastructure.AI;
using MotionTrace.Infrastructure.Logging;

// Explicit integration check against the installed local Python/CUDA environment.
if (args.Length == 2 && args[0] == "--parse-json")
{
    await using var file = File.OpenRead(args[1]);
    var parsed = await AnalysisJson.ReadAsync(file);
    foreach (var athlete in parsed.Athletes)
    {
        var samples = MotionTrace.Core.Motion.MeasurementSources.Barbell(parsed).Extract(parsed.Frames, athlete.Id, MotionTrace.Core.Athletes.Joint.LeftWrist);
        var exercise = parsed.ExercisePredictions.FirstOrDefault(p => p.AthleteId == athlete.Id)?.Exercise;
        if (exercise is MotionTrace.Core.Exercise.ExerciseType.BenchPress or MotionTrace.Core.Exercise.ExerciseType.Squat or MotionTrace.Core.Exercise.ExerciseType.Deadlift)
        {
            var movement = MotionTrace.Core.Motion.MovementAnalyzer.AnalyzeTrajectory(samples, exercise.Value, parsed.Video.Height);
            using var csv = new StringWriter();
            MotionTrace.Core.Motion.MovementCsv.WriteSamples(csv, movement);
            if (movement.Points.Any(p => !double.IsFinite(p.Velocity))) throw new Exception("Non-finite velocity.");
            Console.WriteLine($"Athlete {athlete.Id}: {samples.Count} object measurements; {exercise}; {movement.Reps.Count} reps; {movement.Points.Count} CSV samples.");
        }
        else Console.WriteLine($"Athlete {athlete.Id}: {samples.Count} object measurements; {exercise?.ToString() ?? "legacy prediction"}.");
    }
    var selected = parsed.Athletes.Where(a => a.IsExerciseParticipant).Select(a => a.Id).ToHashSet();
    var filtered = AnalysisSelection.Filter(parsed, selected);
    using var exported = new MemoryStream();
    await AnalysisJson.WriteAsync(exported, filtered);
    exported.Position = 0;
    var roundTrip = await AnalysisJson.ReadAsync(exported);
    bool sameMetadata = System.Text.Json.Nodes.JsonNode.DeepEquals(
        System.Text.Json.Nodes.JsonNode.Parse(roundTrip.VisionMetadataJson ?? "null"),
        System.Text.Json.Nodes.JsonNode.Parse(parsed.VisionMetadataJson ?? "null"));
    if (roundTrip.Frames.Count != parsed.Frames.Count || !sameMetadata ||
        roundTrip.Frames.SelectMany(f => f.Objects).Any(o => o.AthleteId is not {} owner || !selected.Contains(owner)))
        throw new Exception("Filtered export round-trip lost metadata or included unselected objects.");
    Console.WriteLine("PASS: selected-athlete analysis export round-trip and common measurement/CSV path.");
    Console.WriteLine($"PASS: parsed {parsed.Frames.Count} frames, schema {parsed.AnalysisSchemaVersion}; {parsed.Frames.Sum(f => f.Objects.Count)} object observations.");
    return;
}
bool cancelOnly = args.Length == 4 && args[0] == "--cancel-only";
if (cancelOnly) args = args.Skip(1).ToArray();
if (args.Length != 3) throw new ArgumentException("Usage: MotionTrace.Smoke [--cancel-only] <video> <pipeline.py> <data-directory>, or --parse-json <analysis.json>");
var options = PythonOptions.Load();
options.ScriptPath = Path.GetFullPath(args[1]);
options.DataDirectory = Path.GetFullPath(args[2]);
var engine = new PythonPoseEngine(options, new AppLog());
var events = new List<AnalysisProgress>();
var progress = new InlineProgress(p => { events.Add(p); if (p.Fraction is null) Console.WriteLine(p.Stage); });
using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(10));
if (!cancelOnly)
{
var first = await engine.AnalyzeAsync(Path.GetFullPath(args[0]), progress, timeout.Token);
if (first.Frames.Count == 0 || first.Athletes.Count == 0) throw new Exception("Expected real detected poses in the integration fixture.");
Console.WriteLine($"PASS: parsed {first.Frames.Count} frames, {first.Athletes.Count} tracks; schema {first.AnalysisSchemaVersion}.");
events.Clear();
var watch = Stopwatch.StartNew();
var cached = await engine.AnalyzeAsync(Path.GetFullPath(args[0]), progress, timeout.Token);
if (!events.Any(e => e.Stage.Contains("cached", StringComparison.OrdinalIgnoreCase)) || cached.Frames.Count != first.Frames.Count)
    throw new Exception("Cache hit was not observed.");
Console.WriteLine($"PASS: verified content/model/config cache hit in {watch.Elapsed.TotalSeconds:0.0}s.");
}

using var cancel = new CancellationTokenSource();
var runs = Path.Combine(options.DataDirectory, "runs");
int priorRuns = Directory.Exists(runs) ? Directory.EnumerateFileSystemEntries(runs).Count() : 0;
// Wait for actual SAM inference, so cancellation covers the nested vision child.
var cancellationProgress = new InlineProgress(p =>
{
    if (p.Stage.Contains("Tracking objects with SAM", StringComparison.Ordinal) && p.Fraction > .70) cancel.Cancel();
});
try
{
    await engine.AnalyzeAsync(Path.GetFullPath(args[0]), cancellationProgress, cancel.Token);
    throw new Exception("Cancellation did not stop analysis.");
}
catch (OperationCanceledException) when (cancel.IsCancellationRequested)
{
    if (Directory.Exists(runs) && Directory.EnumerateFileSystemEntries(runs).Count() != priorRuns) throw new Exception("Cancelled run left temporary files.");
    Console.WriteLine("PASS: cancelled the actual Python process and cleaned its run directory.");
}

sealed class InlineProgress(Action<AnalysisProgress> report) : IProgress<AnalysisProgress>
{
    public void Report(AnalysisProgress value) => report(value);
}
