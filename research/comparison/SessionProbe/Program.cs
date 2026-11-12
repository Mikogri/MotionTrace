using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Exercise;
using MotionTrace.Infrastructure.AI;
using MotionTrace.Infrastructure.Logging;

if (args.Length != 5 || args[0] is not ("--analyze" or "--restore-only"))
{
    Console.Error.WriteLine("SessionProbe --analyze|--restore-only <repo> <video> <target.json> <data-directory>");
    return 2;
}
string root = Path.GetFullPath(args[1]), video = Path.GetFullPath(args[2]);
string target = Path.GetFullPath(args[3]), data = Path.GetFullPath(args[4]);
using var queryDocument = JsonDocument.Parse(await File.ReadAllTextAsync(target));
string[] expectedProviders = queryDocument.RootElement.TryGetProperty("points", out _) ? ["tapnextpp"] : AnalysisSession.ProviderIds.ToArray();
var options = new PythonOptions
{
    ScriptPath = Path.Combine(root, "ai", "pipeline.py"),
    DataDirectory = data,
    ModelsRoot = Path.Combine(root, ".models", "vision"),
    SamuraiModelsRoot = Path.Combine(root, ".models", "samurai"),
    PointsModelsRoot = Path.Combine(root, ".models", "points"),
    ExecutablePath = Interpreter("motiontrace"),
    VisionExecutablePath = Interpreter("motiontrace-vision"),
    SamuraiExecutablePath = Interpreter("motiontrace-samurai"),
    PointsExecutablePath = Interpreter("motiontrace-points"),
    Device = "cuda:0"
};
Directory.CreateDirectory(data);
using var cancellation = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cancellation.Cancel(); };
var engine = new ComparisonAnalysisEngine(options, new AppLog());
var events = new List<object>();
var timer = Stopwatch.StartNew();
var progress = new DirectProgress(value =>
{
    var row = new { elapsedSeconds = timer.Elapsed.TotalSeconds, value.Stage, value.Fraction,
        provider = value.Provider?.ProviderId, status = value.Provider?.Status.ToString(),
        states = value.Session.Providers.ToDictionary(p => p.Key, p => p.Value.Status.ToString()) };
    events.Add(row);
    Console.Error.WriteLine(JsonSerializer.Serialize(row));
});
AnalysisSession? session = args[0] == "--analyze"
    ? await engine.AnalyzeAsync(video, target, 1.5, progress, cancellation.Token)
    : await engine.TryRestoreAsync(video, target, 1.5, cancellation.Token);
double analysisSeconds = timer.Elapsed.TotalSeconds;
if (session is null) throw new InvalidDataException("No prepared session restored.");
var before = session.Providers.ToDictionary(p => p.Key, p => p.Value.Snapshot);
foreach (string id in expectedProviders) session.Activate(id); // warm JIT/cache
var switchMilliseconds = new List<double>();
long consumedPoints = 0, consumedReps = 0, consumedCharts = 0;
for (int i = 0; i < 1000; i++)
{
    long start = Stopwatch.GetTimestamp();
    var active = session.Activate(expectedProviders[i % expectedProviders.Length]);
    var snapshot = active.Snapshot;
    if (snapshot is not null)
    {
        if (!ReferenceEquals(snapshot, before[active.ProviderId]))
            throw new InvalidDataException("Selection replaced the precomputed snapshot.");
        if (snapshot.Analysis.Versions.BarbellProvider != active.ProviderId)
            throw new InvalidDataException("Mixed provider data.");
        foreach (var movement in snapshot.Movements)
        {
            consumedPoints += movement.Analysis.Points.Count;
            consumedReps += movement.Analysis.Reps.Count;
            consumedCharts += movement.Charts.Count;
        }
    }
    switchMilliseconds.Add(Stopwatch.GetElapsedTime(start).TotalMilliseconds);
}
timer.Restart();
var restored = await engine.TryRestoreAsync(video, target, 1.5, cancellation.Token);
double restoreSeconds = timer.Elapsed.TotalSeconds;
if (restored is null) throw new InvalidDataException("Newly prepared session did not restore.");
var jsonOptions = new JsonSerializerOptions { WriteIndented = true,
    Converters = { new JsonStringEnumConverter() } };
var report = new
{
    session.SessionId, video, target, data, analysisSeconds, restoreSeconds,
    mode = args[0],
    switchMeasurement = new
    {
        iterations = switchMilliseconds.Count,
        medianMilliseconds = Percentile(.5), p95Milliseconds = Percentile(.95),
        maxMilliseconds = switchMilliseconds.Max(), consumedPoints, consumedReps, consumedCharts,
        scope = "AnalysisSession.Activate and reading precomputed light-data references; excludes WinUI binding, overlay rendering and playback."
    },
    providers = Summary(session), restoredProviders = Summary(restored), events
};
string reportPath = Path.Combine(data, args[0] == "--analyze" ? "probe-report.json" : "restore-report.json");
await File.WriteAllTextAsync(reportPath, JsonSerializer.Serialize(report, jsonOptions));
Console.WriteLine(reportPath);
return expectedProviders.All(id => session.Providers[id].Status == ProviderStatus.Ready)
    && expectedProviders.All(id => restored.Providers[id].Status == ProviderStatus.Ready) ? 0 : 1;

double Percentile(double percentile) => switchMilliseconds.Order().ElementAt((int)((switchMilliseconds.Count - 1) * percentile));
static string Interpreter(string name) => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "miniconda3", "envs", name, "python.exe");
static object[] Summary(AnalysisSession session) => session.Providers.Values.Select(provider => (object)new
{
    provider.ProviderId, provider.Status, provider.ResultPath, provider.Error,
    frames = provider.Snapshot?.Analysis.Frames.Count,
    exercises = provider.Snapshot?.Exercises,
    movements = provider.Snapshot?.Movements.Where(m => m.Key.Source == MovementSource.Barbell).Select(m => new
    {
        m.Key, points = m.Analysis.Points.Count, reps = m.Analysis.Reps.Count,
        phases = m.Analysis.Reps, chartVariants = m.Charts.Count,
        chartSeries = m.Charts.Sum(c => c.Series.Count), m.Analysis.MeasurementSource
    }).ToArray()
}).ToArray();

sealed class DirectProgress(Action<ComparisonProgress> handler) : IProgress<ComparisonProgress>
{
    public void Report(ComparisonProgress value) => handler(value);
}
