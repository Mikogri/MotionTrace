using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.PoseCorrection;
using MotionTrace.Infrastructure.Logging;

namespace MotionTrace.Infrastructure.AI;

public sealed record ComparisonProgress(AnalysisSession Session, string Stage, double? Fraction = null, ProviderResult? Provider = null);

/// <summary>Owns one scheduler process. Presentation selection has no reference to this engine.</summary>
public sealed class ComparisonAnalysisEngine(PythonOptions options, AppLog log)
{
    private sealed record Context(AnalysisSession Session, string Directory, string Fingerprint, ComparisonSnapshotStore Store);
    private sealed record SavedStatus(string ProviderId, ProviderStatus Status, string? ResultPath, string? Error);

    public Task<AnalysisSession?> TryImportLegacyAsync(string videoPath, string targetPath, double threshold = 1.5,
        CancellationToken token = default) => Task.Run(async () =>
    {
        // A legacy initialization must never be presented as the user's newly selected physical point.
        if (File.Exists(targetPath)) return null;
        var context = await CreateContextAsync(videoPath, targetPath, threshold, token);
        await RestoreAsync(context, token);
        if (context.Session.Providers.Values.Any(p => p.Status == ProviderStatus.Ready)) return context.Session;
        var runs = Path.Combine(options.DataDirectory, "runs");
        if (!Directory.Exists(runs)) return null;
        var videoHash = await ComparisonSnapshotStore.HashFileAsync(videoPath, token);
        foreach (var file in Directory.EnumerateDirectories(runs).Select(d => new FileInfo(Path.Combine(d, "analysis.json")))
            .Where(f => f.Exists).OrderByDescending(f => f.LastWriteTimeUtc))
        {
            token.ThrowIfCancellationRequested();
            try
            {
                await using var stream = file.OpenRead();
                using var document = await JsonDocument.ParseAsync(stream, cancellationToken: token);
                var root = document.RootElement;
                if (GetString(root, "videoHash") != videoHash || !root.TryGetProperty("versions", out var versions) ||
                    GetString(versions, "barbellProvider") != "grounding_dino_sam2") continue;
                stream.Position = 0;
                var raw = await AnalysisJson.ReadAsync(stream, token);
                var corrected = new TemporalPoseCorrector(options.Correction, new LightPoseSmoother()).Correct(raw, token);
                var snapshot = ProviderPreparation.Prepare(corrected, videoPath, threshold, token);
                var provider = new ProviderResult("grounding_dino_sam2", ProviderStatus.Ready, snapshot, file.FullName);
                await context.Store.SaveAsync(context.Fingerprint, provider, token);
                context.Session.Update(provider);
                await SaveStatusesAsync(context, token);
                return context.Session;
            }
            catch (Exception ex) when (ex is IOException or JsonException or InvalidDataException or ArgumentException)
            { log.Write($"Legacy analysis cannot be restored: {ex.Message}"); }
        }
        return null;
    }, token);

    public Task<AnalysisSession?> TryRestoreAsync(string videoPath, string targetPath, double threshold = 1.5,
        CancellationToken token = default) => Task.Run(() => RestoreSessionAsync(videoPath, targetPath, threshold, token), token);

    private async Task<AnalysisSession?> RestoreSessionAsync(string videoPath, string targetPath, double threshold,
        CancellationToken token)
    {
        var context = await CreateContextAsync(videoPath, targetPath, threshold, token);
        await RestoreAsync(context, token);
        return context.Session.Providers.Values.Any(p => p.Status != ProviderStatus.NotAnalyzed) ? context.Session : null;
    }

    public Task<AnalysisSession> AnalyzeAsync(string videoPath, string targetPath, double threshold,
        IProgress<ComparisonProgress> progress, CancellationToken token, IReadOnlyList<string>? providers = null)
        => Task.Run(() => AnalyzeSessionAsync(videoPath, targetPath, threshold, progress, token, providers), CancellationToken.None);

    private async Task<AnalysisSession> AnalyzeSessionAsync(string videoPath, string targetPath, double threshold,
        IProgress<ComparisonProgress> progress, CancellationToken token, IReadOnlyList<string>? providers)
    {
        var context = await CreateContextAsync(videoPath, targetPath, threshold, token);
        await RestoreAsync(context, token);
        var session = context.Session;
        using var targetDocument = JsonDocument.Parse(session.TargetJson);
        bool pairedTarget = targetDocument.RootElement.TryGetProperty("points", out _);
        if (pairedTarget && providers is not null && providers.Any(id => id != "tapnextpp"))
            throw new ArgumentException("Two-point analysis uses TAPNext++ only.");
        var scheduled = providers?.ToArray() ?? (pairedTarget ? ["tapnextpp"] : AnalysisSession.ProviderIds.ToArray());
        if (scheduled.Length == 0 || scheduled.Distinct().Count() != scheduled.Length || scheduled.Any(p => !AnalysisSession.ProviderIds.Contains(p)))
            throw new ArgumentException("Choose comparison providers explicitly; the custom detector is not part of this session.");
        Directory.CreateDirectory(context.Directory);
        foreach (var id in scheduled) if (session.Providers[id].Status != ProviderStatus.Ready)
            session.Update(new(id, ProviderStatus.Queued));
        progress.Report(new(session, "All comparison tasks scheduled"));
        var pending = scheduled.Where(id => session.Providers[id].Status != ProviderStatus.Ready).ToArray();
        if (pending.Length == 0) return session;
        var outputPath = Path.Combine(context.Directory, "session.json");
        var start = CreateStartInfo(videoPath, targetPath, outputPath, pending);
        using var process = new Process { StartInfo = start };
        var completed = new HashSet<string>(session.Providers.Where(p => p.Value.Status == ProviderStatus.Ready).Select(p => p.Key));
        var prepared = new HashSet<string>();
        async Task HandleAsync(JsonElement message)
        {
            var stage = GetString(message, "stage") ?? "Analyzing";
            double? fraction = message.TryGetProperty("fraction", out var number) && number.ValueKind == JsonValueKind.Number && number.TryGetDouble(out var value) && double.IsFinite(value)
                ? Math.Clamp(value, 0, 1) : null;
            var providerId = GetString(message, "providerId");
            if (providerId is null) { progress.Report(new(session, stage, fraction)); return; }
            if (!AnalysisSession.ProviderIds.Contains(providerId)) throw new InvalidDataException("Scheduler returned an unknown provider.");
            if (!scheduled.Contains(providerId)) return;
            if (completed.Contains(providerId)) return;
            var statusText = GetString(message, "status") ?? "Running";
            if (statusText is "TrackingReady" or "Ready")
            {
                if (!prepared.Add(providerId)) return;
                var resultPath = GetString(message, "resultPath") ?? throw new InvalidDataException("Completed tracking is missing its result path.");
                resultPath = Path.GetFullPath(resultPath, context.Directory);
                var preparing = new ProviderResult(providerId, ProviderStatus.Preparing, ResultPath: resultPath);
                session.Update(preparing); progress.Report(new(session, "Preparing measurements", fraction, preparing));
                try
                {
                    var snapshot = await Task.Run(async () =>
                    {
                        await using var stream = File.OpenRead(resultPath);
                        var raw = await AnalysisJson.ReadAsync(stream, token);
                        if (raw.Versions.BarbellProvider != providerId)
                            throw new InvalidDataException("Tracking output identifies a different provider.");
                        var corrected = new TemporalPoseCorrector(options.Correction, new LightPoseSmoother()).Correct(raw, token);
                        return ProviderPreparation.Prepare(corrected, videoPath, threshold, token);
                    }, token);
                    var ready = new ProviderResult(providerId, ProviderStatus.Ready, snapshot, resultPath);
                    await context.Store.SaveAsync(context.Fingerprint, ready, token);
                    session.Update(ready); completed.Add(providerId);
                    await SaveStatusesAsync(context, CancellationToken.None);
                    progress.Report(new(session, "Ready", 1, ready));
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                {
                    log.Write(ex.ToString());
                    var failed = new ProviderResult(providerId, ProviderStatus.Failed, ResultPath: resultPath, Error: ex.Message);
                    session.Update(failed); progress.Report(new(session, "Preparation failed", null, failed));
                }
            }
            else
            {
                if (!Enum.TryParse<ProviderStatus>(statusText, true, out var status) || status == ProviderStatus.Ready)
                    throw new InvalidDataException($"Unknown scheduler state: {statusText}.");
                var update = new ProviderResult(providerId, status, ResultPath: GetString(message, "resultPath"), Error: GetString(message, "error"));
                session.Update(update); progress.Report(new(session, stage, fraction, update));
            }
        }
        Task? stdout = null;
        Task<string>? stderr = null;
        try
        {
            token.ThrowIfCancellationRequested();
            process.Start();
            stdout = ReadProtocolAsync(process.StandardOutput, HandleAsync);
            stderr = ReadErrorsAsync(process.StandardError);
            var exit = process.WaitForExitAsync(token);
            // A broken stdout consumer must not leave a child blocked on a full pipe.
            var first = await Task.WhenAny(exit, stdout);
            if (first == stdout && stdout.IsFaulted) await stdout;
            await exit;
            await Task.WhenAll(stdout, stderr);
            token.ThrowIfCancellationRequested();
            if (File.Exists(outputPath))
            {
                using var manifest = JsonDocument.Parse(await File.ReadAllTextAsync(outputPath, token));
                if (manifest.RootElement.TryGetProperty("target", out var resolvedTarget) && resolvedTarget.ValueKind == JsonValueKind.Object)
                    session.SetResolvedTarget(resolvedTarget.GetRawText());
                if (manifest.RootElement.TryGetProperty("providers", out var results))
                    foreach (var result in results.EnumerateArray())
                        if (scheduled.Contains(GetString(result, "providerId"))) await HandleAsync(result);
            }
            foreach (string id in pending)
                if (session.Providers[id].Status is ProviderStatus.Queued or ProviderStatus.Running or ProviderStatus.Preparing)
                    session.Update(new(id, ProviderStatus.Failed, Error: process.ExitCode == 0
                        ? "The scheduler ended without a complete provider result." : await stderr));
            if (process.ExitCode != 0) log.Write($"Comparison scheduler exited {process.ExitCode}: {await stderr}");
        }
        catch (OperationCanceledException)
        {
            await StopAsync(process, stdout, stderr);
            session.CancelPending();
            progress.Report(new(session, "Cancelled; completed results retained"));
        }
        catch (Exception ex)
        {
            await StopAsync(process, stdout, stderr);
            foreach (string id in pending)
                if (session.Providers[id].Status != ProviderStatus.Ready)
                    session.Update(new(id, ProviderStatus.Failed, Error: ex.Message));
            log.Write(ex.ToString());
            progress.Report(new(session, "Analysis failed; completed results retained"));
        }
        finally { await SaveStatusesAsync(context, CancellationToken.None); }
        return session;
    }

    private ProcessStartInfo CreateStartInfo(string videoPath, string targetPath, string outputPath, string[] providers)
    {
        if (options.TapNextResolution is not (256 or 512))
            throw new ArgumentException("TAPNext++ resolution must be 256 or 512 with the matching official checkpoint.");
        if (!Path.IsPathFullyQualified(options.ExecutablePath) || !File.Exists(options.ExecutablePath))
            throw new FileNotFoundException("Configure an explicit pose Python interpreter.", options.ExecutablePath);
        if (!File.Exists(options.ComparisonScriptPath)) throw new FileNotFoundException("Comparison scheduler was not deployed.", options.ComparisonScriptPath);
        var start = new ProcessStartInfo(options.ExecutablePath)
        {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true,
            WorkingDirectory = Path.GetDirectoryName(options.ScriptPath)!
        };
        foreach (var argument in new[] { "-u", options.ComparisonScriptPath, "--input", videoPath, "--output", outputPath,
            "--target", targetPath, "--cache", Path.Combine(options.DataDirectory, "comparison-cache"),
            "--pose-python", options.ExecutablePath, "--vision-python", options.VisionExecutablePath,
            "--samurai-python", options.SamuraiExecutablePath, "--points-python", options.PointsExecutablePath,
            "--models-root", options.ModelsRoot, "--samurai-models-root", options.EffectiveSamuraiModelsRoot,
            "--points-models-root", options.EffectivePointsModelsRoot, "--device", options.Device,
            "--pose-model", options.PoseModel, "--pose-weights", options.PoseWeights,
            "--crop-padding", options.CropPadding.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--tapnext-resolution", options.TapNextResolution.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--tapnext-checkpoint", options.EffectiveTapNextCheckpoint,
            "--providers", string.Join(",", providers) }) start.ArgumentList.Add(argument);
        start.Environment["HF_HUB_OFFLINE"] = "1";
        start.Environment["TRANSFORMERS_OFFLINE"] = "1";
        start.Environment["HF_HUB_DISABLE_TELEMETRY"] = "1";
        start.Environment["PYTHONIOENCODING"] = "utf-8";
        var pythonDirectory = Path.GetDirectoryName(options.ExecutablePath)!;
        start.Environment["PATH"] = pythonDirectory + ";" + Path.Combine(pythonDirectory, "Library", "bin") + ";" + start.Environment["PATH"];
        return start;
    }
    private async Task<Context> CreateContextAsync(string videoPath, string targetPath, double threshold, CancellationToken token)
    {
        var videoHash = await ComparisonSnapshotStore.HashFileAsync(videoPath, token);
        var targetJson = File.Exists(targetPath) ? await File.ReadAllTextAsync(targetPath, token) : "{}";
        using var target = JsonDocument.Parse(targetJson);
        var identity = new StringBuilder(videoHash).Append(targetJson).Append(threshold.ToString("R", System.Globalization.CultureInfo.InvariantCulture))
            .Append(ProviderPreparation.Version).Append(typeof(ProviderPreparation).Module.ModuleVersionId)
            .Append(typeof(ComparisonAnalysisEngine).Module.ModuleVersionId).Append(JsonSerializer.Serialize(options.Correction))
            .Append(options.PoseModel).Append(options.PoseWeights).Append(options.Device).Append(options.CropPadding)
            .Append(options.TapNextResolution).Append(options.TapNextCheckpoint);
        if (!string.IsNullOrWhiteSpace(options.TapNextCheckpoint))
        {
            string checkpoint = options.EffectiveTapNextCheckpoint;
            identity.Append(File.Exists(checkpoint) ? await ComparisonSnapshotStore.HashFileAsync(checkpoint, token) : "missing-checkpoint");
        }
        identity.Append(JsonSerializer.Serialize(new[] { options.ExecutablePath, options.VisionExecutablePath,
            options.SamuraiExecutablePath, options.PointsExecutablePath }));
        foreach (var configuredPath in new[] { options.PoseModel, options.PoseWeights }.Where(p => !string.IsNullOrWhiteSpace(p)))
        {
            // Resolve relative files as the scheduler does, and invalidate even when a file is
            // replaced at the same path. Model aliases have no local artifact to fingerprint.
            var artifactPath = Path.GetFullPath(configuredPath, Path.GetDirectoryName(Path.GetFullPath(options.ScriptPath))!);
            identity.Append("\npose-artifact:").Append(artifactPath).Append(':')
                .Append(File.Exists(artifactPath) ? await ComparisonSnapshotStore.HashFileAsync(artifactPath, token) : "missing-or-alias");
        }
        foreach (var root in new[] { options.ModelsRoot, options.EffectiveSamuraiModelsRoot, options.EffectivePointsModelsRoot })
        {
            var manifest = Path.Combine(root, "manifest.json");
            identity.Append(root).Append(File.Exists(manifest) ? await ComparisonSnapshotStore.HashFileAsync(manifest, token) : "missing");
        }
        var codeRoot = Path.GetDirectoryName(options.ScriptPath)!;
        foreach (var relative in new[] { "comparison", "vision", "motiontrace_ai" })
        {
            var folder = Path.Combine(codeRoot, relative);
            if (Directory.Exists(folder)) foreach (var file in Directory.EnumerateFiles(folder, "*.py", SearchOption.AllDirectories).Order(StringComparer.Ordinal))
                identity.Append(Path.GetRelativePath(codeRoot, file)).Append(await ComparisonSnapshotStore.HashFileAsync(file, token));
        }
        var fingerprint = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(identity.ToString()))).ToLowerInvariant();
        var directory = Path.Combine(options.DataDirectory, "comparison-sessions", fingerprint);
        var session = new AnalysisSession(fingerprint, Path.GetFullPath(videoPath), targetJson);
        if (target.RootElement.TryGetProperty("points", out _)) session.Activate("tapnextpp");
        return new(session, directory, fingerprint, new(directory));
    }
    private async Task RestoreAsync(Context context, CancellationToken token)
    {
        var manifestPath = Path.Combine(context.Directory, "session.json");
        if (File.Exists(manifestPath))
        {
            try
            {
                using var manifest = JsonDocument.Parse(await File.ReadAllTextAsync(manifestPath, token));
                if (manifest.RootElement.TryGetProperty("target", out var target) && target.ValueKind == JsonValueKind.Object)
                    context.Session.SetResolvedTarget(target.GetRawText());
            }
            catch (JsonException ex) { log.Write($"Invalid session manifest: {ex.Message}"); }
        }
        var statusesPath = Path.Combine(context.Directory, "prepared-status.json");
        if (File.Exists(statusesPath))
        {
            try
            {
                var statuses = JsonSerializer.Deserialize<SavedStatus[]>(await File.ReadAllTextAsync(statusesPath, token), ComparisonSnapshotStore.Json);
                foreach (var saved in statuses ?? []) if (AnalysisSession.ProviderIds.Contains(saved.ProviderId))
                    context.Session.Update(new(saved.ProviderId, saved.Status == ProviderStatus.Ready ? ProviderStatus.Stale :
                        saved.Status is ProviderStatus.Running or ProviderStatus.Preparing or ProviderStatus.Queued ? ProviderStatus.Cancelled : saved.Status,
                        ResultPath: saved.ResultPath, Error: saved.Error));
            }
            catch (JsonException ex) { log.Write($"Invalid session status cache: {ex.Message}"); }
        }
        foreach (var id in AnalysisSession.ProviderIds)
            if (await context.Store.TryLoadAsync(context.Fingerprint, id, context.Session.VideoPath, token) is {} ready) context.Session.Update(ready);
    }
    private static Task SaveStatusesAsync(Context context, CancellationToken token)
    {
        Directory.CreateDirectory(context.Directory);
        return ComparisonSnapshotStore.AtomicJsonAsync(Path.Combine(context.Directory, "prepared-status.json"),
            context.Session.Providers.Values.Select(p => new SavedStatus(p.ProviderId, p.Status, p.ResultPath, p.Error)).ToArray(), token);
    }
    private async Task ReadProtocolAsync(StreamReader reader, Func<JsonElement, Task> handle)
    {
        while (await reader.ReadLineAsync() is {} line)
        {
            if (!line.StartsWith('{')) { log.Write(line); continue; }
            using var document = JsonDocument.Parse(line);
            await handle(document.RootElement);
        }
    }
    private async Task<string> ReadErrorsAsync(StreamReader reader)
    {
        var tail = new Queue<string>();
        while (await reader.ReadLineAsync() is {} line) { log.Write(line); tail.Enqueue(line); if (tail.Count > 8) tail.Dequeue(); }
        return string.Join(Environment.NewLine, tail);
    }
    private static string? GetString(JsonElement root, string name) => root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
    private static async Task StopAsync(Process process, Task? stdout, Task? stderr)
    {
        try { if (!process.HasExited) process.Kill(entireProcessTree: true); await process.WaitForExitAsync(); }
        catch (InvalidOperationException) { }
        try { await Task.WhenAll(stdout ?? Task.CompletedTask, stderr ?? Task.CompletedTask); }
        catch (Exception) { /* The triggering protocol error is retained by the caller. */ }
    }
}
