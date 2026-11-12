using System.Text.Json.Nodes;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using motion_trace_win.Features.AthleteSelection;
using MotionTrace.Infrastructure.AI;

namespace motion_trace_win.Features.VideoAnalysis;

public sealed partial class AnalysisViewModel
{
    private string activeProviderId = "tapnextpp";
    private string? targetPath;
    private JsonObject target = new();
    private bool sessionStale;
    private bool savingTrackingTarget;
    private bool findingTrackingPoints;
    private int comparisonGeneration;
    private HashSet<int>? rememberedSelection;
    public AnalysisSession? Session { get; private set; }
    public ProviderSnapshot? ActiveSnapshot => !sessionStale ? Session?.ActiveResult.Snapshot : null;
    public bool IsSwitchingProvider { get; private set; }
    public VideoMetadata? LoadedVideo => video;
    private double analysisThreshold = 1.5;
    public double AnalysisThreshold
    {
        get => analysisThreshold;
        set
        {
            if (analysisThreshold == value || !double.IsFinite(value)) return;
            analysisThreshold = value;
            if (Session is not null) sessionStale = true;
            NotifyComparison();
        }
    }
    private static bool ReadNumber(JsonNode? node, out double value)
    {
        value = 0;
        return node is JsonValue number && number.TryGetValue<double>(out value) && double.IsFinite(value);
    }
    private bool ValidTrackingTarget(JsonObject candidate)
    {
        if (candidate.Count == 0) return true;
        if (candidate["points"] is not JsonArray points || points.Count > 2) return false;
        if (points.Count == 0) return true;
        if (video is null || !ReadNumber(candidate["timestampSeconds"], out double timestamp) || timestamp < 0 || timestamp > video.DurationSeconds) return false;
        var read = new List<Point2>();
        foreach (var node in points)
        {
            if (node is not JsonObject point || !ReadNumber(point["x"], out double x) || !ReadNumber(point["y"], out double y) ||
                x < 0 || y < 0 || x >= video.Width || y >= video.Height) return false;
            if (read.Any(p => Math.Abs(p.X-x)<1 && Math.Abs(p.Y-y)<1)) return false;
            read.Add(new(x,y));
        }
        return true;
    }
    public IReadOnlyList<Point2> SelectedTrackingPoints => ValidTrackingTarget(target) && target["points"] is JsonArray points
        ? points.OfType<JsonObject>().Select(p => new Point2(p["x"]!.GetValue<double>(), p["y"]!.GetValue<double>())).ToArray() : [];
    public int TrackingPointCount => SelectedTrackingPoints.Count;
    public double? TrackingTimestamp => ReadNumber(target["timestampSeconds"],out var timestamp) ? timestamp : null;
    public bool HasTarget => ValidTrackingTarget(target) && TrackingPointCount == 2;
    public bool CanEditTrackingPoints => !IsBusy && !savingTrackingTarget && VideoPath is not null;
    public bool CanRemoveTrackingPoints => CanEditTrackingPoints && TrackingPointCount > 0;
    public string TargetNote => findingTrackingPoints ? "Finding barbell…" : HasTarget ? "Two points saved · TAPNext++" : $"Mark two points on the barbell · {TrackingPointCount}/2";
    public string[] ProviderItems => AnalysisSession.ProviderIds.Select(ProviderLabel).ToArray();
    public string SessionSummary => VideoPath is null ? "No video" : IsAnalyzing ? "Analyzing" : findingTrackingPoints ? "Finding barbell" : !HasTarget ? "Waiting for points"
        : sessionStale ? "Outdated" : Session?.ActiveResult.Status == ProviderStatus.Ready ? "Analyzed"
        : Session?.ActiveResult.Status == ProviderStatus.Failed || !string.IsNullOrEmpty(Error) ? "Error"
        : Session?.ActiveResult.Status == ProviderStatus.Cancelled ? "Cancelled" : "Ready to analyze";

    private async Task LoadTargetAndSessionAsync(string hash)
    {
        int generation = ++comparisonGeneration;
        Session = null; sessionStale = false; rememberedSelection = null;
        target = new();
        string path = Path.Combine(options.DataDirectory, "tapnext-targets", hash + ".json");
        targetPath = path;
        JsonObject loaded = new();
        try
        {
            if (File.Exists(path)) loaded = JsonNode.Parse(await File.ReadAllTextAsync(path, lifetime.Token)) as JsonObject
                ?? throw new System.Text.Json.JsonException("Expected a tracking target object.");
        }
        catch (System.Text.Json.JsonException) { Error = "Saved tracking points are invalid. Mark two points again."; }
        if (generation != comparisonGeneration) return;
        if (ValidTrackingTarget(loaded)) target = loaded;
        else Error = "Saved tracking points are invalid. Mark two points again.";
        if (HasTarget)
        {
            var restored = await comparisonEngine.TryRestoreAsync(VideoPath!, path, AnalysisThreshold, lifetime.Token);
            if (generation != comparisonGeneration) return;
            Session = restored;
            Session?.Activate(activeProviderId);
            ApplyActiveProvider();
        }
        // A saved empty target represents Clear; never silently undo that choice.
        if (!File.Exists(path) && generation == comparisonGeneration)
            await SuggestTrackingPointsAsync();
        NotifyComparison();
    }

    private async Task SuggestTrackingPointsAsync()
    {
        findingTrackingPoints = true;
        NotifyComparison();
        try
        {
            var start = new System.Diagnostics.ProcessStartInfo(options.ExecutablePath)
            {
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true
            };
            start.ArgumentList.Add(Path.Combine(Path.GetDirectoryName(options.ScriptPath)!, "comparison", "seed_points.py"));
            start.ArgumentList.Add("--input"); start.ArgumentList.Add(VideoPath!);
            start.ArgumentList.Add("--device"); start.ArgumentList.Add(options.Device);
            start.Environment["PYTHONIOENCODING"] = "utf-8";
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
            timeout.CancelAfter(TimeSpan.FromSeconds(30));
            using var process = System.Diagnostics.Process.Start(start) ?? throw new IOException("Cannot start shaft detection.");
            using var cancellation = timeout.Token.Register(() => { try { process.Kill(true); } catch (InvalidOperationException) { } });
            var output = process.StandardOutput.ReadToEndAsync(timeout.Token);
            var errors = process.StandardError.ReadToEndAsync(timeout.Token);
            await process.WaitForExitAsync(timeout.Token);
            string json = await output, error = await errors;
            if (process.ExitCode != 0) throw new IOException(error);
            if (JsonNode.Parse(json) is JsonObject proposed && ValidTrackingTarget(proposed) && proposed["points"] is JsonArray { Count: 2 })
                await PersistTrackingTargetAsync(proposed);
        }
        catch (Exception ex) when (!lifetime.IsCancellationRequested)
        { log.Write($"Automatic shaft points unavailable; manual selection retained: {ex.Message}"); }
        finally { findingTrackingPoints = false; NotifyComparison(); }
    }

    public async Task ImportComparisonTargetAsync(string path)
    {
        if (targetPath is null || IsBusy) return;
        var parsed = JsonNode.Parse(await File.ReadAllTextAsync(path, lifetime.Token))?.AsObject()
            ?? throw new InvalidDataException("Invalid tracking points.");
        if (!ValidTrackingTarget(parsed) || parsed["points"] is not JsonArray { Count: 2 }) throw new InvalidDataException("Select two tracking points.");
        await PersistTrackingTargetAsync(parsed);
    }

    // Kept for old diagnostic callers; a point never silently replaces both new queries.
    public Task SaveTargetAsync(double timestamp, double[]? point, double[]? box, int athleteId = 0) =>
        point is { Length: 2 } ? AddTrackingPointAsync(timestamp, new(point[0], point[1])) : Task.CompletedTask;

    public Task AddTrackingPointAsync(double timestamp, Point2 point)
    {
        if (!CanEditTrackingPoints || TrackingPointCount >= 2 || video is null) return Task.CompletedTask;
        if (!double.IsFinite(timestamp) || timestamp < 0 || timestamp > video.DurationSeconds) throw new ArgumentOutOfRangeException(nameof(timestamp));
        if (!double.IsFinite(point.X) || !double.IsFinite(point.Y) || point.X < 0 || point.Y < 0 || point.X >= video.Width || point.Y >= video.Height)
            throw new ArgumentOutOfRangeException(nameof(point));
        if (TrackingTimestamp is {} queryTime && Math.Abs(queryTime - timestamp) > .001)
            throw new InvalidOperationException("Both points must be marked on the same paused frame.");
        if (SelectedTrackingPoints.Any(p => Math.Abs(p.X-point.X)<1 && Math.Abs(p.Y-point.Y)<1))
            throw new InvalidOperationException("Choose a different second point on the barbell.");
        var updated = target.DeepClone().AsObject();
        updated["targetId"] = "bar-reference";
        updated["athleteTrackId"] = 0;
        updated["initializationVersion"] = 2;
        updated["timestampSeconds"] = TrackingTimestamp ?? timestamp;
        var points = updated["points"] as JsonArray ?? new JsonArray();
        if (updated["points"] is null) updated["points"] = points;
        points.Add(new JsonObject { ["x"] = point.X, ["y"] = point.Y });
        return PersistTrackingTargetAsync(updated);
    }

    public Task UndoTrackingPointAsync()
    {
        if (!CanRemoveTrackingPoints) return Task.CompletedTask;
        var updated = target.DeepClone().AsObject();
        ((JsonArray)updated["points"]!).RemoveAt(TrackingPointCount-1);
        if (((JsonArray)updated["points"]!).Count == 0) updated.Remove("timestampSeconds");
        return PersistTrackingTargetAsync(updated);
    }

    public Task ClearTrackingPointsAsync() => CanEditTrackingPoints ? PersistTrackingTargetAsync(new()) : Task.CompletedTask;

    private async Task PersistTrackingTargetAsync(JsonObject updated)
    {
        if (targetPath is null) return;
        string path = targetPath;
        int generation = ++comparisonGeneration;
        // Publish the preview immediately, but analysis waits for the atomic disk commit.
        var previous = target;
        target = updated;
        savingTrackingTarget = true;
        sessionStale = Session is not null;
        Error = "";
        NotifyComparison();
        if (sessionStale) ApplyActiveProvider();
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            string temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            await File.WriteAllTextAsync(temporary, updated.ToJsonString(), lifetime.Token);
            File.Move(temporary, path, true);
        }
        catch
        {
            if (generation == comparisonGeneration && targetPath == path) target = previous;
            throw;
        }
        finally { savingTrackingTarget = false; NotifyComparison(); }
    }

    private void NotifyComparison()
    {
        foreach (string name in new[] { nameof(ProviderItems), nameof(SessionSummary), nameof(AnalysisStateText), nameof(TargetNote),
            nameof(SelectedTrackingPoints), nameof(TrackingPointCount), nameof(TrackingTimestamp), nameof(CanEditTrackingPoints), nameof(CanRemoveTrackingPoints), nameof(HasTarget), nameof(CanAnalyze), nameof(CanUseAnalysisButton), nameof(NeedsReanalysis) }) Changed(name);
    }

    private void ApplyActiveProvider()
    {
        IsSwitchingProvider = true;
        if (selection is not null) rememberedSelection = Athletes.Where(a => IsSelected(a.Id)).Select(a => a.Id).ToHashSet();
        var snapshot = ActiveSnapshot;
        classifications.Clear();
        resolvedExercises = snapshot?.Exercises.ToDictionary(p => p.Key, p => p.Value) ?? [];
        Athletes.Clear(); selection = null;
        if (snapshot is not null)
        {
            var participants = AnalysisSelection.ParticipantIds(snapshot.Analysis);
            if (participants.Count > 0)
            {
                selection = new(participants);
                if (rememberedSelection is not null)
                    foreach (int id in participants.Where(id => !rememberedSelection.Contains(id))) selection.TrySetSelected(id, false);
            }
            foreach (var athlete in snapshot.Analysis.Athletes.Where(a => participants.Contains(a.Id)))
                Athletes.Add(new(athlete.Id, athlete.DisplayName) { IsSelected = selection?.Contains(athlete.Id) == true });
        }
        completedProvider = activeProviderId;
        IsSwitchingProvider = false;
        Result = snapshot?.Analysis;
        Changed(nameof(AthleteCount)); Changed(nameof(TrackingNote)); Changed(nameof(CanCorrectObjects));
        Status = SessionSummary;
        Error = Session?.ActiveResult.Error ?? "";
        NotifyComparison();
    }

    public async Task RunComparisonAsync(IReadOnlyList<string>? providers = null)
    {
        if (!CanAnalyze || targetPath is null) return;
        using var source = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        int generation = ++comparisonGeneration;
        SetAnalysisProgress(0);
        IReadOnlyList<string> scheduled = ["tapnextpp"];
        var providerProgress = scheduled.ToDictionary(id => id, _ => 0d);
        double sharedProgress = 0;
        operation = source; IsBusy = true; IsAnalyzing = true; Error = ""; sessionStale = false;
        try
        {
            var reporter = new Progress<ComparisonProgress>(p =>
            {
                if (generation != comparisonGeneration || source.IsCancellationRequested) return;
                Session = p.Session; Session.Activate(activeProviderId);
                Status = p.Stage;
                // Shared preparation and each tracker count as one work unit.
                // Fractions can restart at each model stage, so preserve the high-water mark.
                if (p.Provider is null && p.Fraction is {} sharedFraction)
                    sharedProgress = Math.Max(sharedProgress, sharedFraction);
                if (p.Provider is {} provider && providerProgress.ContainsKey(provider.ProviderId))
                {
                    if (provider.Status is ProviderStatus.Running or ProviderStatus.Preparing or ProviderStatus.Ready)
                        sharedProgress = 1;
                    if (p.Fraction is {} fraction)
                        providerProgress[provider.ProviderId] = Math.Max(providerProgress[provider.ProviderId], .95 * fraction);
                }
                var results = Session.Providers;
                foreach (string id in scheduled)
                    if (results[id].Status is ProviderStatus.Ready or ProviderStatus.Failed or ProviderStatus.NotInstalled)
                        providerProgress[id] = 1;
                int percent = (int)(100 * (sharedProgress + providerProgress.Values.Sum()) / (scheduled.Count + 1));
                SetAnalysisProgress(Math.Max(analysisProgressPercent, Math.Min(percent, 99)));
                if (p.Provider?.ProviderId == activeProviderId)
                {
                    if (p.Provider.Status == ProviderStatus.Ready) ApplyActiveProvider();
                    else Error = p.Provider.Error ?? "";
                }
                NotifyComparison();
            });
            Session = await comparisonEngine.AnalyzeAsync(VideoPath!, targetPath, AnalysisThreshold, reporter, source.Token, scheduled);
            if (generation != comparisonGeneration) return;
            if (scheduled.All(id => Session.Providers[id].Status == ProviderStatus.Ready)) SetAnalysisProgress(100);
            Session.Activate(activeProviderId); ApplyActiveProvider();
        }
        catch (OperationCanceledException) { Status = "Cancelled · completed results retained"; }
        catch (Exception ex) { ReportError(ex); }
        finally { operation = null; IsAnalyzing = false; IsBusy = false; NotifyComparison(); }
    }
}
