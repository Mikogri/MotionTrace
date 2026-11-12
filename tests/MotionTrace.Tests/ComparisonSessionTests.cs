using System.Text.Json;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;
using MotionTrace.Infrastructure.AI;
using MotionTrace.Infrastructure.Logging;

namespace MotionTrace.Tests;

public sealed class ComparisonSessionTests
{
    [Fact]
    public void AnalyzeQueuesAllFourAndNeverCustomDetector()
    {
        var session = new AnalysisSession("test", "video.mp4", "{}");
        session.QueueAll();
        Assert.Equal(4, session.Providers.Count);
        Assert.All(session.Providers.Values, p => Assert.Equal(ProviderStatus.Queued, p.Status));
        Assert.DoesNotContain("custom_barbell", session.Providers.Keys);
    }

    [Fact]
    public void SwitchingUsesSamePreparedObjectsAndCannotMixProviderSources()
    {
        var session = new AnalysisSession("test", "video.mp4", "{}");
        var first = ProviderPreparation.Prepare(CreateAnalysis("tapnextpp", 1), "video.mp4");
        var second = ProviderPreparation.Prepare(CreateAnalysis("bootstapir", 2), "video.mp4");
        session.Update(new("tapnextpp", ProviderStatus.Ready, first));
        session.Update(new("bootstapir", ProviderStatus.Ready, second));
        for (int i = 0; i < 100; i++)
        {
            Assert.Same(first, session.Activate("tapnextpp").Snapshot);
            Assert.Same(second, session.Activate("bootstapir").Snapshot);
        }
        Assert.Throws<ArgumentException>(() => session.Update(new("samurai", ProviderStatus.Ready, first)));
        Assert.Throws<ArgumentException>(() => session.Update(new("samurai", ProviderStatus.Ready)));
        var key = new MovementKey(1, ExerciseType.BenchPress, MovementSource.Barbell, 1.5);
        Assert.Single(first.FindMovement(key)!.Analysis.Reps);
        Assert.Equal(2, second.FindMovement(key)!.Analysis.Reps.Count);
        Assert.Same(first.FindMovement(key)!.Analysis, session.Activate("tapnextpp").Snapshot!.FindMovement(key)!.Analysis);
    }

    [Fact]
    public void FailureAndCancellationPreserveCompleteIndependentResults()
    {
        var session = new AnalysisSession("test", "video.mp4", "{}");
        session.QueueAll();
        var snapshot = ProviderPreparation.Prepare(CreateAnalysis("tapnextpp", 1), "video.mp4");
        session.Update(new("tapnextpp", ProviderStatus.Ready, snapshot));
        session.Update(new("samurai", ProviderStatus.Failed, Error: "out of memory"));
        session.CancelPending();
        Assert.Same(snapshot, session.Providers["tapnextpp"].Snapshot);
        Assert.Equal(ProviderStatus.Failed, session.Providers["samurai"].Status);
        Assert.Equal("out of memory", session.Providers["samurai"].Error);
        Assert.Equal(ProviderStatus.Cancelled, session.Providers["bootstapir"].Status);
        Assert.Equal(ProviderStatus.Cancelled, session.Providers["grounding_dino_sam2"].Status);
        Assert.Null(session.Activate("bootstapir").Snapshot);
    }

    [Fact]
    public void RepMappingUsesTimeInsteadOfOrdinal()
    {
        var snapshot = ProviderPreparation.Prepare(CreateAnalysis("tapnextpp", 2), "video.mp4");
        var key = new MovementKey(1, ExerciseType.BenchPress, MovementSource.Barbell, 1.5);
        var reps = snapshot.FindMovement(key)!.Analysis.Reps;
        Assert.Equal(2, reps.Count);
        Assert.Equal(reps[1], AnalysisSession.MatchRepAt(snapshot, key, (reps[1].Start + reps[1].End) / 2));
        Assert.Null(AnalysisSession.MatchRepAt(snapshot, key, 100));
    }

    [Fact]
    public async Task PreparedCacheRoundTripsAllMetricsAndInvalidatesTargetOrCorruptArtifacts()
    {
        var directory = Path.Combine(Path.GetTempPath(), "MotionTrace-comparison-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var store = new ComparisonSnapshotStore(directory);
            foreach (string id in new[] { "tapnextpp", "bootstapir" })
            {
                var raw = CreateAnalysis(id, id == "tapnextpp" ? 1 : 2);
                var rawPath = Path.Combine(directory, id + ".json");
                await using (var stream = File.Create(rawPath)) await AnalysisJson.WriteAsync(stream, raw);
                var prepared = ProviderPreparation.Prepare(raw, "video.mp4");
                await store.SaveAsync("video-target-calibration-version", new(id, ProviderStatus.Ready, prepared, rawPath));
                var restored = await store.TryLoadAsync("video-target-calibration-version", id, "video.mp4");
                Assert.NotNull(restored);
                Assert.Equal(9, restored.Snapshot!.Movements.Count);
                var key = new MovementKey(1, ExerciseType.BenchPress, MovementSource.Barbell, 1.5);
                Assert.Equal(prepared.FindMovement(key)!.Analysis.Points, restored.Snapshot.FindMovement(key)!.Analysis.Points);
                Assert.Equal(prepared.FindMovement(key)!.Analysis.Reps.Count, restored.Snapshot.FindMovement(key)!.Analysis.Reps.Count);
                Assert.Equal(prepared.FindMovement(key)!.States, restored.Snapshot.FindMovement(key)!.States);
                Assert.Equal(4, restored.Snapshot.FindMovement(key)!.Charts.Count);
                Assert.Null(await store.TryLoadAsync("different-target", id, "video.mp4"));
            }
            await File.AppendAllTextAsync(Path.Combine(directory, "tapnextpp.json"), " ");
            Assert.Null(await store.TryLoadAsync("video-target-calibration-version", "tapnextpp", "video.mp4"));
            Assert.NotNull(await store.TryLoadAsync("video-target-calibration-version", "bootstapir", "video.mp4"));
            await File.AppendAllTextAsync(Path.Combine(directory, "bootstapir.prepared.json"), " ");
            Assert.Null(await store.TryLoadAsync("video-target-calibration-version", "bootstapir", "video.mp4"));
        }
        finally { Directory.Delete(directory, true); }
    }

    [Theory]
    [InlineData("tapnextpp")]
    [InlineData("bootstapir")]
    public async Task PointTrackersTransportObservedPointWithoutFabricatedBox(string provider)
    {
        var original = CreateAnalysis(provider, 1);
        await using var stream = new MemoryStream();
        await AnalysisJson.WriteAsync(stream, original);
        stream.Position = 0;
        var result = await AnalysisJson.ReadAsync(stream);
        Assert.Null(result.Frames[0].Objects[0].Box);
        Assert.Equal(provider, result.Frames[0].Objects[0].Measurement!.Source);
    }

    [Fact]
    public async Task MaskTrackerCannotOmitObjectBoxAndPretendPointIsMeasured()
    {
        var original = CreateAnalysis("grounding_dino_sam2", 1);
        await using var stream = new MemoryStream();
        await AnalysisJson.WriteAsync(stream, original);
        stream.Position = 0;
        await Assert.ThrowsAsync<InvalidDataException>(() => AnalysisJson.ReadAsync(stream));
    }

    [Fact]
    public async Task LegacyImportRequiresVideoHashAndLeavesOtherProvidersNotAnalyzed()
    {
        var directory = Path.Combine(Path.GetTempPath(), "MotionTrace-legacy-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(directory, "runs", "old"));
        try
        {
            var video = Path.Combine(directory, "video.mp4");
            var target = Path.Combine(directory, "target.json");
            await File.WriteAllTextAsync(video, "video identity for cache test");
            var hash = await VideoCorrections.HashAsync(video, default);
            var raw = CreateAnalysis("grounding_dino_sam2", 1);
            raw = raw with { VideoHash = "wrong-video", Frames = raw.Frames.Select(f => f with
            {
                Objects = f.Objects.Select(o => o with { Box = new(200, 100, 200, 500) }).ToArray()
            }).ToArray() };
            var path = Path.Combine(directory, "runs", "old", "analysis.json");
            await using (var stream = File.Create(path)) await AnalysisJson.WriteAsync(stream, raw);
            var engine = new ComparisonAnalysisEngine(new() { DataDirectory = directory }, new AppLog());
            Assert.Null(await engine.TryImportLegacyAsync(video, target));
            await using (var stream = File.Create(path)) await AnalysisJson.WriteAsync(stream, raw with { VideoHash = hash });
            var imported = await engine.TryImportLegacyAsync(video, target);
            Assert.NotNull(imported);
            Assert.Equal(ProviderStatus.Ready, imported.Providers["grounding_dino_sam2"].Status);
            Assert.All(imported.Providers.Where(p => p.Key != "grounding_dino_sam2"),
                p => Assert.Equal(ProviderStatus.NotAnalyzed, p.Value.Status));
            Assert.NotNull(await engine.TryImportLegacyAsync(video, target));
            await File.WriteAllTextAsync(target, "{\"point\":{\"x\":5,\"y\":6}}");
            Assert.Null(await engine.TryImportLegacyAsync(video, target));
        }
        finally { Directory.Delete(directory, true); }
    }

    [Theory]
    [InlineData("mask.png")]
    [InlineData("raw-observations.json")]
    public async Task PreparedCacheRejectsChangedExternalMasksAndNestedRawObservations(string changedAsset)
    {
        var directory = Path.Combine(Path.GetTempPath(), "MotionTrace-assets-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            await File.WriteAllTextAsync(Path.Combine(directory, "mask.png"), "test mask bytes");
            await File.WriteAllTextAsync(Path.Combine(directory, "raw-observations.json"), "[]");
            var raw = CreateAnalysis("tapnextpp", 1);
            raw = raw with
            {
                VisionMetadataJson = "{\"rawObservationsPath\":\"raw-observations.json\"}",
                Frames = raw.Frames.Select(f => f with { Objects = f.Objects.Select(o => o with { MaskPath = "mask.png" }).ToArray() }).ToArray()
            };
            var path = Path.Combine(directory, "analysis.json");
            await using (var stream = File.Create(path)) await AnalysisJson.WriteAsync(stream, raw);
            var store = new ComparisonSnapshotStore(directory);
            await store.SaveAsync("identity", new("tapnextpp", ProviderStatus.Ready, ProviderPreparation.Prepare(raw, "video.mp4"), path));
            Assert.NotNull(await store.TryLoadAsync("identity", "tapnextpp", "video.mp4"));
            await File.AppendAllTextAsync(Path.Combine(directory, changedAsset), "changed");
            Assert.Null(await store.TryLoadAsync("identity", "tapnextpp", "video.mp4"));
        }
        finally { Directory.Delete(directory, true); }
    }

    internal static AnalysisResult CreateAnalysis(string provider, int repetitions)
    {
        double duration = 2 + repetitions * 4;
        var frames = Enumerable.Range(0, (int)(duration * 30)).Select(i =>
        {
            double time = i / 30.0, phase = (time - 1) % 4;
            double y = time < 1 || time >= 1 + repetitions * 4 ? 200 :
                phase < 1.2 ? 200 + phase / 1.2 * 180 : phase < 1.5 ? 380 :
                phase < 2.7 ? 380 - (phase - 1.5) / 1.2 * 180 : 200;
            return new PoseFrame(time, []) { Objects = [new("target", 1, null, null, .95, TrackingState.Tracked,
                new(new(300, y), provider, AnalysisQuality.Good, false, false, false))] };
        }).ToArray();
        return new(4, new("video.mp4", duration, 800, 800, 30), new("test", "test", "test") { BarbellProvider = provider },
            [new(1, "Athlete 1")], frames, []) { ExercisePredictions = [new(1, ExerciseType.BenchPress, .9, .5, [], "shared-test")] };
    }
}
