using System.Collections.ObjectModel;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Athletes;
using MotionTrace.Infrastructure.AI;
using MotionTrace.Infrastructure.Logging;
using motion_trace_win.Features.AthleteSelection;
using motion_trace_win.Features.VideoImport;
using motion_trace_win.Shared;

namespace motion_trace_win.Features.VideoAnalysis;

public sealed partial class AnalysisViewModel(ComparisonAnalysisEngine comparisonEngine, VideoImportService importer, PythonOptions options, AppLog log, IExerciseClassifier classifier) : ObservableObject, IDisposable
{
    private CancellationTokenSource? operation;
    private readonly CancellationTokenSource lifetime = new();
    private MotionTrace.Core.Athletes.AthleteSelection? selection;
    private Dictionary<int, ExerciseClassification[]> classifications = [];
    private Dictionary<int, ExerciseClassification> resolvedExercises = [];
    private Dictionary<int, ExerciseType> manualExercises = [];
    private VideoCorrections? corrections;
    private IReadOnlyList<ObjectCorrection> objectCorrections = [];
    public int SelectedBarbellModelIndex => AnalysisSession.ProviderIds.ToList().IndexOf(activeProviderId);
    private string? completedProvider;
    public bool NeedsReanalysis => sessionStale;
    public bool CanCorrectObjects => !IsBusy && VideoPath is not null;
    private static string ProviderLabel(string? provider) => provider switch
    { "grounding_dino_sam2" => "DINO/SAM", "samurai" => "SAMURAI", "tapnextpp" => "TAPNext++", "bootstapir" => "BootsTAPIR", "custom_barbell" => "MotionTrace (legacy)", _ => "Unknown model" };
    public Task SelectBarbellModelAsync(int index)
    {
        if (index != AnalysisSession.ProviderIds.ToList().IndexOf("tapnextpp")) return Task.CompletedTask;
        activeProviderId = AnalysisSession.ProviderIds[index];
        Session?.Activate(activeProviderId);
        ApplyActiveProvider();
        Changed(nameof(SelectedBarbellModelIndex));
        return Task.CompletedTask;
    }
    public IEnumerable<string> CorrectedObjectIds(int athleteId) => objectCorrections.Where(o => o.AthleteId == athleteId).Select(o => o.ObjectId).Distinct();
    public ExerciseType ExerciseForAthlete(int athleteId) => manualExercises.TryGetValue(athleteId, out var manual)
        ? manual : DetectedExercise(athleteId);
    public bool HasManualExercise(int athleteId) => manualExercises.ContainsKey(athleteId);
    public string ExerciseSource(int athleteId) => HasManualExercise(athleteId) ? "manual"
        : resolvedExercises.TryGetValue(athleteId, out var resolved) && resolved.ExerciseType != ExerciseType.Unknown ? resolved.Limitation ?? "model"
        : DetectedExercise(athleteId) != ExerciseType.Unknown ? "legacy pose classifier" : "unknown";
    public async Task SetExerciseAsync(int athleteId, ExerciseType exercise)
    {
        if (corrections is null || !Enum.IsDefined(exercise)) return;
        manualExercises[athleteId] = exercise;
        try { await corrections.SaveExercisesAsync(manualExercises, lifetime.Token); }
        catch (Exception ex) { ReportError(ex); }
    }
    public async Task SaveObjectCorrectionAsync(ObjectCorrection correction)
    {
        if (corrections is null || !CanCorrectObjects) throw new InvalidOperationException("Open a video before marking the shared target.");
        await corrections.SaveObjectAsync(correction, lifetime.Token);
        objectCorrections = await corrections.ReadObjectsAsync(lifetime.Token);
        options.CorrectionsPath = corrections.ObjectPath;
        await SaveTargetAsync(correction.TimestampSeconds, correction.Point, correction.Box, correction.AthleteId);
    }
    public int? PreferredMotionAthleteId => classifications.Where(pair=>IsSelected(pair.Key) && pair.Value.Any(c=>c.ExerciseType==ExerciseType.BenchPress)).OrderByDescending(pair => pair.Value.Count(c => c.ExerciseType == ExerciseType.BenchPress)).Select(pair => (int?)pair.Key).FirstOrDefault();
    public ExerciseType DetectedExercise(int athleteId) => resolvedExercises.TryGetValue(athleteId, out var resolved) && resolved.ExerciseType != ExerciseType.Unknown
        ? resolved.ExerciseType
        : Result is { AnalysisSchemaVersion: >= 4 } ? ExerciseType.Unknown
        : classifications.TryGetValue(athleteId,out var timeline)
        ? timeline.Where(c=>c.ExerciseType is ExerciseType.BenchPress or ExerciseType.Squat or ExerciseType.Deadlift)
            .GroupBy(c=>c.ExerciseType).OrderByDescending(g=>g.Count()).Select(g=>g.Key).FirstOrDefault()
        : ExerciseType.Unknown;
    public int SelectedAthleteCount => Athletes.Count(a=>IsSelected(a.Id));
    public bool HasSelectedParticipant => Result?.Athletes.Any(a => a.IsExerciseParticipant && IsSelected(a.Id)) == true;
    public bool CanChooseAthleteManually => CanCorrectObjects && Result is {} analysis && analysis.Athletes.Count > 0
        && AnalysisSelection.ParticipantIds(analysis).Count == 0;
    private string exerciseSummary = "Unknown";
    public string ExerciseSummary { get => exerciseSummary; private set { if(exerciseSummary==value)return;Set(ref exerciseSummary,value);Changed(nameof(ExerciseSummaryItems)); } }
    public string[] ExerciseSummaryItems => exerciseSummary.Split('\n',StringSplitOptions.RemoveEmptyEntries);
    public void UpdateExercise(double seconds)
    {
        var current=Result is {} analyzed?FrameLookup.At(analyzed.Frames,seconds):null;
        foreach(var row in Athletes)row.UpdateTracking(current?.Athletes.FirstOrDefault(p=>p.AthleteId==row.Id));
        var lines = Athletes.Where(a => IsSelected(a.Id)).Select(a =>
        {
            int index = (int)Math.Max(0, Math.Floor(seconds * 2));
            var value = classifications.TryGetValue(a.Id, out var timeline) && index < timeline.Length ? timeline[index] : resolvedExercises.GetValueOrDefault(a.Id);
            if (manualExercises.TryGetValue(a.Id, out var manual)) return $"{a.DisplayName}: {manual} · manual";
            return value is { ExerciseType: not ExerciseType.Unknown }
                ? value.Limitation?.StartsWith(ExerciseResolver.Version, StringComparison.Ordinal) == true
                    ? $"{a.DisplayName}: {value.ExerciseType} · bar + pose"
                    : $"{a.DisplayName}: {value.ExerciseType} · score {value.Confidence:0.00}"
                : value?.Limitation == "No verified object ownership."
                ? $"{a.DisplayName}: Unknown · no verified object ownership"
                : $"{a.DisplayName}: Unknown";
        });
        ExerciseSummary = string.Join("\n", lines);
        if (ExerciseSummary.Length == 0) ExerciseSummary = "Unknown";
    }
    private (Dictionary<int, ExerciseClassification[]> Timelines, Dictionary<int, ExerciseClassification> Resolved) Classify(AnalysisResult analysis, CancellationToken token)
    {
        var resolvedExercises = analysis.Athletes.ToDictionary(a => a.Id, a => ExerciseResolver.Resolve(analysis, a.Id));
        var timelines = analysis.Athletes.ToDictionary(a => a.Id, _ => new ExerciseClassification[(int)Math.Ceiling(analysis.Video.DurationSeconds * 2) + 1]);
        if (analysis.AnalysisSchemaVersion >= 4)
        {
            foreach (var (athleteId, timeline) in timelines)
            {
                var prediction = analysis.ExercisePredictions.FirstOrDefault(p => p.AthleteId == athleteId);
                var resolved = resolvedExercises[athleteId];
                for (int index = 0; index < timeline.Length; index++)
                {
                    token.ThrowIfCancellationRequested();
                    var window = prediction?.Windows.LastOrDefault(w => w.StartSeconds <= index / 2.0 && w.EndSeconds >= index / 2.0);
                    bool ownershipRejected = prediction?.OwnershipGate == "no-verified-object-owner";
                    timeline[index] = resolved.ExerciseType != ExerciseType.Unknown && (window is null || window.Decision == ExerciseType.Unknown)
                        ? resolved
                        : new(ownershipRejected ? ExerciseType.Unknown : window?.Decision ?? ExerciseType.Unknown,
                            prediction?.Score ?? 0, ownershipRejected ? "No verified object ownership." : "X-CLIP score is not a calibrated probability.");
                }
            }
            return (timelines, resolvedExercises);
        }
        int start = 0, stop = 0;
        for (int index = 0; index <= (int)Math.Ceiling(analysis.Video.DurationSeconds * 2); index++)
        {
            token.ThrowIfCancellationRequested();
            double time = index / 2.0;
            while (stop < analysis.Frames.Count && analysis.Frames[stop].TimestampSeconds <= time) stop++;
            while (start < stop && analysis.Frames[start].TimestampSeconds < time - BenchPressClassifier.WindowSeconds) start++;
            var window = Enumerable.Range(start, stop - start).Select(i => analysis.Frames[i]).ToList();
            // Include an empty current frame so gaps cannot preserve an old positive result.
            if (window.Count == 0 || time - window[^1].TimestampSeconds > .01) window.Add(new(time, []));
            foreach (var athlete in analysis.Athletes) timelines[athlete.Id][index] = classifier.Classify(window, athlete.Id);
        }
        foreach (var athlete in analysis.Athletes)
        {
            var resolved = resolvedExercises[athlete.Id];
            if (resolved.ExerciseType == ExerciseType.Unknown) continue;
            var timeline = timelines[athlete.Id];
            for (int index = 0; index < timeline.Length; index++)
                if (timeline[index].ExerciseType == ExerciseType.Unknown) timeline[index] = resolved;
        }
        return (timelines, resolvedExercises);
    }
    private int analysisProgressPercent;
    public string AnalysisProgressText => $"{analysisProgressPercent}%";
    private void SetAnalysisProgress(int percent) => Set(ref analysisProgressPercent, percent, nameof(AnalysisProgressText));
    private bool analyzing;
    public bool IsAnalyzing
    {
        get => analyzing;
        private set
        {
            Set(ref analyzing, value);
            Changed(nameof(AnalysisButtonText));
            Changed(nameof(AnalysisStateText));
            Changed(nameof(CanUseAnalysisButton));
        }
    }
    public string AnalysisButtonText => IsAnalyzing ? "Cancel" : "Analyze video";
    public bool CanUseAnalysisButton => IsAnalyzing || CanAnalyze;
    private bool busy;
    private string? videoPath;
    private VideoMetadata? video;
    private AnalysisResult? result;
    private string status = "Ready to import", error = "";
    public ObservableCollection<AthleteRow> Athletes { get; } = [];
    public double VideoAspectRatio => video is { Height: > 0 } ? (double)video.Width / video.Height : 9.0 / 16;
    public string? VideoPath { get => videoPath; private set { Set(ref videoPath, value); Changed(nameof(AnalysisStateText)); } }
    public AnalysisResult? Result { get => result; private set { Set(ref result, value); Changed(nameof(HasResults)); Changed(nameof(TrackingNote)); Changed(nameof(AnalysisStateText)); Changed(nameof(CanChooseAthleteManually)); } }
    public bool HasResults => Result is not null;
    public string AnalysisStateText => SessionSummary;
    public bool IsBusy
    {
        get => busy;
        private set
        {
            Set(ref busy, value);
            Changed(nameof(CanImport));
            Changed(nameof(CanCorrectObjects));
            Changed(nameof(CanEditTrackingPoints));
            Changed(nameof(CanRemoveTrackingPoints));
            Changed(nameof(CanAnalyze));
            Changed(nameof(CanUseAnalysisButton));
            Changed(nameof(CanChooseAthleteManually));
            Changed(nameof(TrackingNote));
            Changed(nameof(AthleteCount));
        }
    }
    public bool CanImport => !IsBusy;
    public bool CanAnalyze => !IsBusy && !savingTrackingTarget && VideoPath is not null && HasTarget;
    public string Status { get => status; private set => Set(ref status, value); }
    public string Error { get => error; private set { Set(ref error, value); Changed(nameof(HasError)); Changed(nameof(AnalysisStateText)); } }
    public bool HasError => !string.IsNullOrWhiteSpace(Error);
    public string FileName => video?.FileName ?? "Your next session starts here";
    public string VideoDetails => video is null ? "MP4, MOV or AVI · Original file stays in place" :
        $"{video.Width} × {video.Height}   ·   {video.FramesPerSecond:0.##} FPS   ·   {TimeSpan.FromSeconds(video.DurationSeconds):mm\\:ss}";
    public string AthleteCount => !HasResults ? "Awaiting analysis" : CanChooseAthleteManually && Athletes.Count > 0
        ? "Manual correction selection" : $"{Athletes.Count} exercise participants";
    public string TrackingNote => Result is null ? "Analyze a video to detect and select athletes." :
        CanChooseAthleteManually ? Athletes.Count == 0
            ? "No athlete-barbell pair confirmed. Choose an athlete manually to mark the barbell, then analyze again."
            : "Manual selection is for correction only. Mark the barbell and analyze again before exporting." :
        Athletes.Count == 0 ? "No confirmed athletes. Try a clearer view of the athlete and barbell." :
        "Only confirmed exercise participants are shown. At least one participant remains selected.";
    public bool IsSelected(int id) => selection?.Contains(id) == true;

    public void ChooseAthleteForCorrection(int id)
    {
        if (!CanChooseAthleteManually || Result?.Athletes.FirstOrDefault(a => a.Id == id) is not {} athlete) return;
        // This explicit inspection choice does not change the backend's participation decision.
        selection = new([id]);
        Athletes.Clear();
        Athletes.Add(new(id, athlete.DisplayName + " · manual correction") { IsSelected = true });
        Changed(nameof(AthleteCount));
        Changed(nameof(TrackingNote));
        Changed(nameof(SelectedAthleteCount));
    }

    public async Task ImportAsync(string path)
    {
        if (IsBusy) return;
        SetAnalysisProgress(0); IsBusy = true; Error = ""; Status = "Reading video";
        try
        {
            var metadata = await importer.ReadAsync(path, lifetime.Token);
            var hash = await VideoCorrections.HashAsync(path, lifetime.Token);
            corrections = new(options.DataDirectory, hash);
            manualExercises = await corrections.ReadExercisesAsync(lifetime.Token);
            objectCorrections = await corrections.ReadObjectsAsync(lifetime.Token);
            options.CorrectionsPath = corrections.ObjectPath;
            classifications.Clear(); resolvedExercises.Clear(); ExerciseSummary = "Unknown";
            Session = null; rememberedSelection = null;
            video = metadata; VideoPath = path; Result = null; selection = null; Athletes.Clear();
            Changed(nameof(FileName)); Changed(nameof(VideoDetails)); Changed(nameof(AthleteCount));
            await LoadTargetAndSessionAsync(hash);
            Status = SessionSummary;
        }
        catch (OperationCanceledException) { Status = "Import cancelled"; }
        catch (Exception ex) { ReportError(ex); }
        finally { IsBusy = false; }
    }

    public Task AnalyzeAsync() => RunComparisonAsync();

    public bool SetSelected(int id, bool value)
    {
        if (selection is null || !selection.TrySetSelected(id, value))
        { return false; }
        Athletes.Single(a => a.Id == id).IsSelected = value;
        Changed(nameof(SelectedAthleteCount));
        Status = "Athlete selection updated";
        return true;
    }
    public void SetAllSelected(bool value)
    {
        if(selection is null)return;
        selection.SetAllSelected(value);
        foreach(var row in Athletes)row.IsSelected=selection.Contains(row.Id);
        Changed(nameof(SelectedAthleteCount));
        Status=value?"All athletes selected":"One athlete kept selected";
    }
    public void Cancel() => operation?.Cancel();
    public void ReportError(Exception ex) { log.Write(ex.ToString()); Error = ex.Message; Status = "Action failed"; }
    public void Dispose() { lifetime.Cancel(); lifetime.Dispose(); }
}
