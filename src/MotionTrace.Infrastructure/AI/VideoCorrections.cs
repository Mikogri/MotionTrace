using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using MotionTrace.Core.Exercise;

namespace MotionTrace.Infrastructure.AI;

public sealed record ObjectCorrection(string ObjectId, int AthleteId, double TimestampSeconds,
    double[]? Box = null, double[]? Point = null);
public sealed record ObjectCorrections(string VideoHash, IReadOnlyList<ObjectCorrection> Objects);

/// <summary>User corrections are separate from model predictions and are never deleted with an analysis cache.</summary>
public sealed class VideoCorrections(string dataDirectory, string videoHash)
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    { Converters = { new JsonStringEnumConverter() } };
    private string DirectoryPath => Path.Combine(dataDirectory, "corrections");
    public string ObjectPath => Path.Combine(DirectoryPath, ValidHash() + ".objects.json");
    private string ExercisePath => Path.Combine(DirectoryPath, ValidHash() + ".exercises.json");
    private string ValidHash() => videoHash.Length == 64 && videoHash.All(Uri.IsHexDigit)
        ? videoHash.ToLowerInvariant() : throw new ArgumentException("A SHA-256 video identity is required.");

    public static async Task<string> HashAsync(string videoPath, CancellationToken token)
    {
        await using var stream = File.OpenRead(videoPath);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream, token)).ToLowerInvariant();
    }

    public async Task<Dictionary<int, ExerciseType>> ReadExercisesAsync(CancellationToken token = default)
    {
        if (!File.Exists(ExercisePath)) return [];
        var result = JsonSerializer.Deserialize<Dictionary<int, ExerciseType>>(await File.ReadAllTextAsync(ExercisePath, token), Json)
            ?? throw new InvalidDataException("Exercise corrections are empty.");
        if (result.Any(p => p.Key <= 0 || !Enum.IsDefined(p.Value))) throw new InvalidDataException("Invalid exercise correction.");
        return result;
    }

    public Task SaveExercisesAsync(IReadOnlyDictionary<int, ExerciseType> choices, CancellationToken token = default) =>
        WriteAsync(ExercisePath, choices, token);

    public async Task<IReadOnlyList<ObjectCorrection>> ReadObjectsAsync(CancellationToken token = default)
    {
        if (!File.Exists(ObjectPath)) return [];
        var saved = JsonSerializer.Deserialize<ObjectCorrections>(await File.ReadAllTextAsync(ObjectPath, token), Json);
        if (saved is null || saved.VideoHash != videoHash || saved.Objects is null)
            throw new InvalidDataException("Correction belongs to another video or is malformed.");
        return saved.Objects;
    }

    public async Task SaveObjectAsync(ObjectCorrection correction, CancellationToken token = default)
    {
        if (string.IsNullOrWhiteSpace(correction.ObjectId) || correction.AthleteId <= 0 ||
            !double.IsFinite(correction.TimestampSeconds) || correction.TimestampSeconds < 0 ||
            (correction.Box is null && correction.Point is null) ||
            (correction.Box is {} b && (b.Length != 4 || b.Any(x => !double.IsFinite(x) || x < 0) || b[2] <= b[0] || b[3] <= b[1])) ||
            (correction.Point is {} p && (p.Length != 2 || p.Any(x => !double.IsFinite(x) || x < 0))))
            throw new ArgumentException("Invalid object correction.");
        var saved = await ReadObjectsAsync(token);
        if (saved.Any(o => o.AthleteId == correction.AthleteId && o.ObjectId != correction.ObjectId))
            throw new InvalidOperationException("Correct the athlete's existing object so that its identity stays stable.");
        var objects = saved.Where(o => o.ObjectId != correction.ObjectId ||
            Math.Abs(o.TimestampSeconds - correction.TimestampSeconds) > .00001).Append(correction).ToArray();
        await WriteAsync(ObjectPath, new ObjectCorrections(videoHash, objects), token);
    }

    private async Task WriteAsync<T>(string path, T value, CancellationToken token)
    {
        Directory.CreateDirectory(DirectoryPath);
        string temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(value, Json), token);
            File.Move(temporary, path, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
