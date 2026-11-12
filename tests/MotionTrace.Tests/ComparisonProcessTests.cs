using System.Diagnostics;
using System.Text.Json;
using MotionTrace.Core.Analysis;
using MotionTrace.Infrastructure.AI;
using MotionTrace.Infrastructure.Logging;

namespace MotionTrace.Tests;

public sealed class ComparisonProcessTests
{
    [PythonAvailableFact]
    public async Task TwoPointsRunOnlyTapNextAndRestoreItsActiveSnapshot()
    {
        using var fixture = await Fixture.CreateAsync(cancel: false);
        await File.WriteAllTextAsync(fixture.Target, "{\"initializationVersion\":2,\"points\":[{\"x\":1,\"y\":1},{\"x\":5,\"y\":5}]}");
        var engine = new ComparisonAnalysisEngine(fixture.Options, new AppLog());
        var session = await engine.AnalyzeAsync(fixture.Video, fixture.Target, 1.5, new InlineProgress(_ => { }), default);
        Assert.Equal("tapnextpp", session.ActiveProviderId);
        Assert.Equal(ProviderStatus.Ready, session.ActiveResult.Status);
        Assert.All(session.Providers.Values.Where(p => p.ProviderId != "tapnextpp"), p => Assert.Equal(ProviderStatus.NotAnalyzed, p.Status));
        Assert.Equal("tapnextpp", (await File.ReadAllTextAsync(fixture.Invocations)).Trim());
        var restored = await engine.TryRestoreAsync(fixture.Video, fixture.Target);
        Assert.Equal("tapnextpp", restored!.ActiveProviderId);
        fixture.Options.TapNextResolution = 512;
        Assert.Null(await engine.TryRestoreAsync(fixture.Video, fixture.Target));
    }

    [PythonAvailableFact]
    public async Task SchedulerRunsOnceAndRestoreDoesNotLaunchInference()
    {
        using var fixture = await Fixture.CreateAsync(cancel: false);
        var engine = new ComparisonAnalysisEngine(fixture.Options, new AppLog());
        var session = await engine.AnalyzeAsync(fixture.Video, fixture.Target, 1.5, new InlineProgress(_ => { }), default);
        Assert.Equal(ProviderStatus.Ready, session.Providers["tapnextpp"].Status);
        Assert.Equal(ProviderStatus.Ready, session.Providers["bootstapir"].Status);
        Assert.Equal(ProviderStatus.Failed, session.Providers["samurai"].Status);
        Assert.Equal(ProviderStatus.NotInstalled, session.Providers["grounding_dino_sam2"].Status);
        var restored = await engine.TryRestoreAsync(fixture.Video, fixture.Target);
        Assert.NotNull(restored);
        Assert.Equal(2, restored.Providers.Values.Count(p => p.Status == ProviderStatus.Ready));
        Assert.Equal(ProviderStatus.Failed, restored.Providers["samurai"].Status);
        Assert.Single(await File.ReadAllLinesAsync(fixture.Invocations));
        var request = await File.ReadAllTextAsync(fixture.Invocations);
        Assert.Contains("grounding_dino_sam2,samurai,tapnextpp,bootstapir", request);
        Assert.DoesNotContain("custom_barbell", request);
        foreach (var id in AnalysisSession.ProviderIds) restored.Activate(id);
        Assert.Single(await File.ReadAllLinesAsync(fixture.Invocations));
        await File.WriteAllTextAsync(fixture.Target, "{\"point\":{\"x\":2,\"y\":1}}");
        Assert.Null(await engine.TryRestoreAsync(fixture.Video, fixture.Target));
    }

    [PythonAvailableFact]
    public async Task PreparedCacheInvalidatesWhenExplicitPoseFilesChangeInPlace()
    {
        using var fixture = await Fixture.CreateAsync(cancel: false);
        var configuration = Path.Combine(fixture.Directory, "pose-config.py");
        var weights = Path.Combine(fixture.Directory, "pose-weights.pth");
        await File.WriteAllTextAsync(configuration, "configuration-v1");
        await File.WriteAllTextAsync(weights, "weights-v1");
        fixture.Options.PoseModel = configuration;
        fixture.Options.PoseWeights = weights;
        var engine = new ComparisonAnalysisEngine(fixture.Options, new AppLog());
        await engine.AnalyzeAsync(fixture.Video, fixture.Target, 1.5, new InlineProgress(_ => { }), default);
        Assert.NotNull(await engine.TryRestoreAsync(fixture.Video, fixture.Target));
        await File.WriteAllTextAsync(configuration, "configuration-v2");
        Assert.Null(await engine.TryRestoreAsync(fixture.Video, fixture.Target));
        await File.WriteAllTextAsync(configuration, "configuration-v1");
        Assert.NotNull(await engine.TryRestoreAsync(fixture.Video, fixture.Target));
        await File.WriteAllTextAsync(weights, "weights-v2");
        Assert.Null(await engine.TryRestoreAsync(fixture.Video, fixture.Target));
        await File.WriteAllTextAsync(weights, "weights-v1");
        Assert.NotNull(await engine.TryRestoreAsync(fixture.Video, fixture.Target));
        foreach (var name in new[] { nameof(PythonOptions.ExecutablePath), nameof(PythonOptions.VisionExecutablePath),
            nameof(PythonOptions.SamuraiExecutablePath), nameof(PythonOptions.PointsExecutablePath) })
        {
            var property = typeof(PythonOptions).GetProperty(name)!;
            var previous = property.GetValue(fixture.Options);
            property.SetValue(fixture.Options, Path.Combine(fixture.Directory, name, "python.exe"));
            Assert.Null(await engine.TryRestoreAsync(fixture.Video, fixture.Target));
            property.SetValue(fixture.Options, previous);
        }
        Assert.NotNull(await engine.TryRestoreAsync(fixture.Video, fixture.Target));
        Assert.Single(await File.ReadAllLinesAsync(fixture.Invocations));
    }

    [PythonAvailableFact]
    public async Task CancellationKillsChildTreeAndKeepsReadySnapshot()
    {
        using var fixture = await Fixture.CreateAsync(cancel: true);
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        var engine = new ComparisonAnalysisEngine(fixture.Options, new AppLog());
        var progress = new InlineProgress(p => { if (p.Provider?.Status == ProviderStatus.Ready) cancellation.Cancel(); });
        var session = await engine.AnalyzeAsync(fixture.Video, fixture.Target, 1.5, progress, cancellation.Token);
        Assert.Equal(ProviderStatus.Ready, session.Providers["tapnextpp"].Status);
        Assert.Equal(ProviderStatus.Cancelled, session.Providers["samurai"].Status);
        Assert.Equal(ProviderStatus.Cancelled, session.Providers["bootstapir"].Status);
        var childId = int.Parse(await File.ReadAllTextAsync(Path.Combine(fixture.Directory, "child.pid")));
        try { using var child = Process.GetProcessById(childId); Assert.True(child.HasExited); }
        catch (ArgumentException) { /* The OS has already removed the killed process. */ }
        var restored = await engine.TryRestoreAsync(fixture.Video, fixture.Target);
        Assert.Equal(ProviderStatus.Ready, restored!.Providers["tapnextpp"].Status);
    }

    private sealed class InlineProgress(Action<ComparisonProgress> action) : IProgress<ComparisonProgress>
    { public void Report(ComparisonProgress value) => action(value); }

    private sealed class Fixture : IDisposable
    {
        public string Directory { get; } = Path.Combine(Path.GetTempPath(), "MotionTrace session process " + Guid.NewGuid().ToString("N"));
        public string Video => Path.Combine(Directory, "video with spaces.mp4");
        public string Target => Path.Combine(Directory, "target.json");
        public string Invocations => Path.Combine(Directory, "calls.txt");
        public PythonOptions Options { get; private set; } = new();
        public static async Task<Fixture> CreateAsync(bool cancel)
        {
            var fixture = new Fixture();
            var ai = Path.Combine(fixture.Directory, "ai");
            System.IO.Directory.CreateDirectory(Path.Combine(ai, "comparison"));
            fixture.Options = new() { ScriptPath = Path.Combine(ai, "pipeline.py"), DataDirectory = Path.Combine(fixture.Directory, "data"),
                ModelsRoot = Path.Combine(fixture.Directory, "models", "vision") };
            await File.WriteAllTextAsync(fixture.Video, "Test process only; no real video inference.");
            await File.WriteAllTextAsync(fixture.Target, "{\"point\":{\"x\":1,\"y\":1}}");
            foreach (var id in new[] { "tapnextpp", "bootstapir" })
            {
                await using var file = File.Create(Path.Combine(fixture.Directory, id + ".json"));
                await AnalysisJson.WriteAsync(file, ComparisonSessionTests.CreateAnalysis(id, 1));
            }
            var script = """
                import argparse, json, pathlib, subprocess, sys, time
                p=argparse.ArgumentParser()
                p.add_argument('--input'); p.add_argument('--output'); p.add_argument('--target'); p.add_argument('--providers')
                args, rest=p.parse_known_args()
                root=pathlib.Path(args.input).parent
                with (root/'calls.txt').open('a') as f: f.write(args.providers+'\n')
                def event(**x): print(json.dumps(x), flush=True)
                event(stage='Shared preparation', fraction=None, providerId=None)
                for provider in args.providers.split(','): event(providerId=provider, status='Queued', fraction=None)
                if CANCEL:
                    child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
                    (root/'child.pid').write_text(str(child.pid))
                event(providerId='tapnextpp', status='TrackingReady', resultPath=str(root/'tapnextpp.json'))
                if CANCEL:
                    time.sleep(120)
                else:
                    event(providerId='samurai', status='Failed', error='Test model failure')
                    event(providerId='grounding_dino_sam2', status='NotInstalled', error='Test absent weights')
                    event(providerId='bootstapir', status='TrackingReady', resultPath=str(root/'bootstapir.json'))
                """;
            await File.WriteAllTextAsync(fixture.Options.ComparisonScriptPath, "CANCEL=" + (cancel ? "True" : "False") + "\n" + script);
            return fixture;
        }
        public void Dispose() => System.IO.Directory.Delete(Directory, recursive: true);
    }
}

public sealed class PythonAvailableFactAttribute : FactAttribute
{
    public PythonAvailableFactAttribute()
    {
        if (!File.Exists(new PythonOptions().ExecutablePath)) Skip = "Explicit MotionTrace Python environment is not installed; process protocol test requires Python, no models/GPU.";
    }
}
