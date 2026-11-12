using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using MotionTrace.Core.Analysis;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;

namespace MotionTrace.Infrastructure.AI;

/// <summary>Tracking and prepared measurements are separate immutable artifacts; the index is committed last.</summary>
public sealed class ComparisonSnapshotStore(string directory)
{
    internal static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        Converters = { new JsonStringEnumConverter() }, IgnoreReadOnlyProperties = true
    };
    private sealed record MovementData(MovementKey Key, MovementAnalysis Analysis, ExerciseStatus[] States);
    private sealed record SnapshotData(int SchemaVersion, string Fingerprint, string ProviderId, string TrackingPath,
        string TrackingHash, string CorrectedPath, string CorrectedHash, IReadOnlyList<MovementData> Movements,
        Dictionary<int, ExerciseClassification> Exercises, SortedDictionary<string, string> AssetHashes);

    public async Task SaveAsync(string fingerprint, ProviderResult provider, CancellationToken token = default)
    {
        if (provider.Status != ProviderStatus.Ready || provider.Snapshot is not {} snapshot || provider.ResultPath is null)
            throw new ArgumentException("Only complete results can be saved.");
        Directory.CreateDirectory(directory);
        var stem = Path.Combine(directory, provider.ProviderId + "-" + Guid.NewGuid().ToString("N"));
        var correctedPath = stem + ".analysis.json";
        await using (var stream = File.Create(correctedPath + ".tmp"))
            await AnalysisJson.WriteAsync(stream, snapshot.Analysis, token);
        File.Move(correctedPath + ".tmp", correctedPath);
        var assets = await HashAssetsAsync(provider.ResultPath, snapshot.Analysis, token);
        var data = new SnapshotData(2, fingerprint, provider.ProviderId, Path.GetFullPath(provider.ResultPath),
            await HashFileAsync(provider.ResultPath, token), correctedPath, await HashFileAsync(correctedPath, token),
            snapshot.Movements.Select(m => new MovementData(m.Key, m.Analysis, m.States)).ToArray(), snapshot.Exercises.ToDictionary(), assets);
        var path = Path.Combine(directory, provider.ProviderId + ".prepared.json");
        await AtomicJsonAsync(path, data, token);
        await AtomicJsonAsync(path + ".sha256", await HashFileAsync(path, token), token);
    }

    public async Task<ProviderResult?> TryLoadAsync(string fingerprint, string providerId, string videoPath,
        CancellationToken token = default)
    {
        var path = Path.Combine(directory, providerId + ".prepared.json");
        if (!File.Exists(path) || !File.Exists(path + ".sha256")) return null;
        try
        {
            var digest = JsonSerializer.Deserialize<string>(await File.ReadAllTextAsync(path + ".sha256", token));
            if (digest != await HashFileAsync(path, token)) return null;
            await using var dataStream = File.OpenRead(path);
            var saved = await JsonSerializer.DeserializeAsync<SnapshotData>(dataStream, Json, token);
            if (saved is null || saved.SchemaVersion != 2 || saved.Fingerprint != fingerprint || saved.ProviderId != providerId ||
                !File.Exists(saved.TrackingPath) || !File.Exists(saved.CorrectedPath) ||
                saved.TrackingHash != await HashFileAsync(saved.TrackingPath, token) ||
                saved.CorrectedHash != await HashFileAsync(saved.CorrectedPath, token)) return null;
            foreach (var asset in saved.AssetHashes)
                if (!File.Exists(asset.Key) || asset.Value != await HashFileAsync(asset.Key, token)) return null;
            await using var stream = File.OpenRead(saved.CorrectedPath);
            var analysis = await AnalysisJson.ReadAsync(stream, token);
            if (analysis.Versions.BarbellProvider != providerId) return null;
            // Rebuild only lightweight projections at open time; no tracking, smoothing, velocity, or rep detection.
            var movements = saved.Movements.Select(m => new PreparedMovement(m.Key, m.Analysis, m.States,
                (from metric in Enum.GetValues<MotionChartMetric>() from axis in Enum.GetValues<MotionChartAxis>()
                 select new PreparedChart(metric, axis, RepChartData.Create(videoPath, m.Analysis,
                     m.Analysis.Reps.Select(r => r.Number).ToHashSet(), metric, axis))).ToArray())).ToArray();
            return new(providerId, ProviderStatus.Ready, new(analysis, movements, saved.Exercises), saved.TrackingPath);
        }
        catch (Exception ex) when (ex is IOException or JsonException or InvalidDataException or ArgumentException)
        { return null; } // Invalid cache is never displayed as Ready. Analyze explicitly rebuilds it.
    }

    internal static async Task<string> HashFileAsync(string path, CancellationToken token)
    {
        await using var stream = File.OpenRead(path);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream, token)).ToLowerInvariant();
    }

    private static async Task<SortedDictionary<string, string>> HashAssetsAsync(string trackingPath, AnalysisResult analysis,
        CancellationToken token)
    {
        var baseDirectory = Path.GetDirectoryName(Path.GetFullPath(trackingPath))!;
        var paths = analysis.Frames.SelectMany(f => f.Objects).Select(o => o.MaskPath)
            .Where(p => !string.IsNullOrWhiteSpace(p)).Select(p => Path.GetFullPath(p!, baseDirectory))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        await using var stream = File.OpenRead(trackingPath);
        using var document = await JsonDocument.ParseAsync(stream, cancellationToken: token);
        void ReadRawPath(JsonElement element)
        {
            if (element.ValueKind != JsonValueKind.Object) return;
            if (element.TryGetProperty("rawObservationsPath", out var path) && path.ValueKind == JsonValueKind.String &&
                !string.IsNullOrWhiteSpace(path.GetString())) paths.Add(Path.GetFullPath(path.GetString()!, baseDirectory));
        }
        ReadRawPath(document.RootElement);
        foreach (var name in new[] { "backend", "visionMetadata" })
            if (document.RootElement.TryGetProperty(name, out var metadata)) ReadRawPath(metadata);
        var hashes = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (var path in paths.Order(StringComparer.Ordinal)) hashes[path] = await HashFileAsync(path, token);
        return hashes;
    }
    internal static async Task AtomicJsonAsync<T>(string path, T data, CancellationToken token)
    {
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        await using (var stream = File.Create(temporary)) await JsonSerializer.SerializeAsync(stream, data, Json, token);
        token.ThrowIfCancellationRequested();
        File.Move(temporary, path, true);
    }
}
