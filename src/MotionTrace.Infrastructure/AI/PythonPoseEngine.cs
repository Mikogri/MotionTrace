using System.Diagnostics;
using System.Text.Json;
using MotionTrace.Core.Analysis;
using MotionTrace.Infrastructure.Logging;

namespace MotionTrace.Infrastructure.AI;

public sealed class PythonPoseEngine(PythonOptions options, AppLog log) : IPoseAnalysisEngine
{
    public async Task<AnalysisResult> AnalyzeAsync(string videoPath, IProgress<AnalysisProgress> progress, CancellationToken cancellationToken)
    {
        if (!File.Exists(options.ScriptPath)) throw new FileNotFoundException("Python adapter was not deployed.", options.ScriptPath);
        if (!Path.IsPathFullyQualified(options.ExecutablePath) || !File.Exists(options.ExecutablePath))
            throw new FileNotFoundException("Configure the explicit pose environment python.exe path.", options.ExecutablePath);
        if (options.BarbellProvider is not ("grounding_dino_sam2" or "custom_barbell"))
            throw new InvalidOperationException("Unknown barbell provider. No fallback was started.");
        if (options.BarbellProvider == "grounding_dino_sam2" &&
            (!Path.IsPathFullyQualified(options.VisionExecutablePath) || !File.Exists(options.VisionExecutablePath)))
            throw new FileNotFoundException("Vision environment is unavailable. Run setup-vision.ps1 first. The custom detector has not been started.", options.VisionExecutablePath);
        log.Write($"Vision model directory: {options.ModelsRoot}; adapter: {options.ScriptPath}");
        if (options.BarbellProvider == "grounding_dino_sam2" &&
            (!Path.IsPathFullyQualified(options.ModelsRoot) || !File.Exists(Path.Combine(options.ModelsRoot, "manifest.json"))))
            throw new FileNotFoundException($"Vision model manifest was not found at: {Path.Combine(options.ModelsRoot, "manifest.json")}. Check ModelsRoot in settings.json.");
        var runDirectory = Path.Combine(options.DataDirectory, "runs", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDirectory);
        var resultPath = Path.Combine(runDirectory, "analysis.json");
        var start = new ProcessStartInfo(options.ExecutablePath)
        {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true,
            RedirectStandardError = true, WorkingDirectory = Path.GetDirectoryName(options.ScriptPath)!
        };
        foreach (var argument in new[] { "-u", options.ScriptPath, "--input", videoPath, "--output", resultPath,
            "--cache", Path.Combine(options.DataDirectory, "cache"), "--device", options.Device, "--pose-model", options.PoseModel, "--pose-weights", options.PoseWeights, "--crop-padding", options.CropPadding.ToString(System.Globalization.CultureInfo.InvariantCulture) }) start.ArgumentList.Add(argument);
        foreach (var argument in new[] { "--vision-python", options.VisionExecutablePath, "--models-root", options.ModelsRoot, "--provider", options.BarbellProvider }) start.ArgumentList.Add(argument);
        if (options.BarbellProvider == "grounding_dino_sam2" && options.CorrectionsPath is {} corrections && File.Exists(corrections))
        { start.ArgumentList.Add("--corrections"); start.ArgumentList.Add(corrections); }
        start.Environment["HF_HUB_OFFLINE"] = "1";
        start.Environment["HF_HUB_DISABLE_TELEMETRY"] = "1";
        start.Environment["PYTHONIOENCODING"] = "utf-8";
        // Conda DLL lookup also needs Library/bin when launched without `conda activate`.
        var executableDirectory = Path.GetDirectoryName(options.ExecutablePath);
        if (!string.IsNullOrEmpty(executableDirectory))
            start.Environment["PATH"] = executableDirectory + ";" + Path.Combine(executableDirectory, "Library", "bin") + ";" + start.Environment["PATH"];
        using var process = new Process { StartInfo = start };
        bool preserveArtifacts = false;
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            log.Write($"Starting pose analysis: {videoPath}");
            process.Start();
            var stdout = ReadProgressAsync(process.StandardOutput, progress);
            var stderr = ReadErrorsAsync(process.StandardError);
            try { await process.WaitForExitAsync(cancellationToken); }
            catch (OperationCanceledException)
            {
                if (!process.HasExited) process.Kill(entireProcessTree: true);
                await process.WaitForExitAsync(CancellationToken.None);
                await Task.WhenAll(stdout, stderr);
                log.Write("Pose analysis cancelled; process tree stopped.");
                throw;
            }
            await Task.WhenAll(stdout, stderr);
            cancellationToken.ThrowIfCancellationRequested();
            if (process.ExitCode != 0)
                throw new InvalidOperationException($"Analysis failed (exit {process.ExitCode}): {await stderr}");
            progress.Report(new("Finalizing"));
            await using var stream = File.OpenRead(resultPath);
            var result = await Task.Run(() => AnalysisJson.ReadAsync(stream, cancellationToken), cancellationToken);
            preserveArtifacts = result.AnalysisSchemaVersion >= 4;
            log.Write($"Pose analysis completed: {result.Frames.Count} frames, {result.Athletes.Count} tracks.");
            return result;
        }
        finally
        {
            // Only the uniquely owned run directory is removed; completed reusable cache stays intact.
            try { if (!preserveArtifacts) Directory.Delete(runDirectory, recursive: true); }
            catch (IOException ex) { log.Write(ex.Message); }
            catch (UnauthorizedAccessException ex) { log.Write(ex.Message); }
        }
    }

    private async Task ReadProgressAsync(StreamReader reader, IProgress<AnalysisProgress> progress)
    {
        while (await reader.ReadLineAsync() is { } line)
        {
            if (!line.StartsWith("{", StringComparison.Ordinal)) { log.Write(line); continue; }
            try
            {
                using var json = JsonDocument.Parse(line);
                var root = json.RootElement;
                if (root.TryGetProperty("stage", out var stage))
                {
                    double? fraction = root.TryGetProperty("fraction", out var number) && number.TryGetDouble(out var value) && double.IsFinite(value)
                        ? Math.Clamp(value, 0, 1) : null;
                    progress.Report(new(stage.GetString() ?? "Analyzing", fraction));
                }
                else log.Write(line);
            }
            catch (JsonException) { log.Write(line); }
        }
    }

    private async Task<string> ReadErrorsAsync(StreamReader reader)
    {
        var tail = new Queue<string>();
        while (await reader.ReadLineAsync() is { } line)
        {
            log.Write(line);
            tail.Enqueue(line);
            if (tail.Count > 6) tail.Dequeue();
        }
        // The complete traceback is already in the log. Keep its final cause visible in the InfoBar.
        return tail.LastOrDefault(line => !string.IsNullOrWhiteSpace(line)) ?? "The AI process did not report a cause. See the MotionTrace log.";
    }
}
