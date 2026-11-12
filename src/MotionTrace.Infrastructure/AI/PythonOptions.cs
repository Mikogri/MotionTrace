using System.Text.Json;

namespace MotionTrace.Infrastructure.AI;

public sealed class PythonOptions
{
    public string ExecutablePath { get; set; } = DefaultPython();
    public string PoseModel { get; set; } = "rtmpose-l_8xb256-420e_body8-384x288";
    public string PoseWeights { get; set; } = "";
    public double CropPadding { get; set; } = .2;
    public MotionTrace.Core.PoseCorrection.PoseCorrectionOptions Correction { get; set; } = new();
    public string Device { get; set; } = "cuda:0";
    public string ScriptPath { get; set; } = Path.Combine(AppContext.BaseDirectory, "ai", "pipeline.py");
    public string VisionExecutablePath { get; set; } = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "miniconda3", "envs", "motiontrace-vision", "python.exe");
    public string SamuraiExecutablePath { get; set; } = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "miniconda3", "envs", "motiontrace-samurai", "python.exe");
    public string PointsExecutablePath { get; set; } = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "miniconda3", "envs", "motiontrace-points", "python.exe");
    public string ComparisonScriptPath => Path.Combine(Path.GetDirectoryName(ScriptPath)!, "comparison", "analyze_session.py");
    public string SamuraiModelsRoot { get; set; } = "";
    public string PointsModelsRoot { get; set; } = "";
    public int TapNextResolution { get; set; } = 256;
    public string TapNextCheckpoint { get; set; } = "";
    public string EffectiveTapNextCheckpoint => string.IsNullOrWhiteSpace(TapNextCheckpoint) ? ""
        : Path.GetFullPath(TapNextCheckpoint, EffectivePointsModelsRoot);
    public string EffectiveSamuraiModelsRoot => string.IsNullOrWhiteSpace(SamuraiModelsRoot) ? Path.Combine(Path.GetDirectoryName(ModelsRoot)!, "samurai") : SamuraiModelsRoot;
    public string EffectivePointsModelsRoot => string.IsNullOrWhiteSpace(PointsModelsRoot) ? Path.Combine(Path.GetDirectoryName(ModelsRoot)!, "points") : PointsModelsRoot;
    public string ModelsRoot { get; set; } = FindProjectModelsRoot(AppContext.BaseDirectory) ?? FindInstalledModelsRoot(
        Environment.GetEnvironmentVariable("LOCALAPPDATA"),
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "AppData", "Local"));
    public string BarbellProvider { get; set; } = "custom_barbell";
    public string? CorrectionsPath { get; set; }
    public string DataDirectory { get; set; } = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MotionTrace");

    private static string DefaultPython()
    {
        var candidate = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "miniconda3", "envs", "motiontrace", "python.exe");
        return candidate;
    }

    public static string FindInstalledModelsRoot(params string?[] localDataDirectories)
    {
        // The installer uses LOCALAPPDATA. A debugger or packaged host can expose
        // a different known-folder path; locate the same installed model set.
        var candidates = localDataDirectories.Where(p => !string.IsNullOrWhiteSpace(p) && Path.IsPathFullyQualified(p))
            .Select(p => Path.Combine(p!, "MotionTrace", "models", "vision"))
            .Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        if (candidates.Length == 0) throw new InvalidOperationException("Cannot resolve the local model installation directory.");
        return candidates.FirstOrDefault(p => File.Exists(Path.Combine(p, "manifest.json"))) ?? candidates[0];
    }

    public static string? FindProjectModelsRoot(string applicationDirectory)
    {
        // AppData can be virtualized by the host launching the installer. A
        // project-local model store is shared by Visual Studio and the EXE.
        for (var directory = new DirectoryInfo(applicationDirectory); directory is not null; directory = directory.Parent)
        {
            var candidate = Path.Combine(directory.FullName, ".models", "vision");
            if (File.Exists(Path.Combine(candidate, "manifest.json"))) return candidate;
        }
        return null;
    }

    public static PythonOptions Load(string? dataDirectory = null)
    {
        var defaults = new PythonOptions();
        if (dataDirectory is not null) defaults.DataDirectory = dataDirectory;
        var path = Path.Combine(defaults.DataDirectory, "settings.json");
        if (!File.Exists(path)) return defaults;
        var saved = JsonSerializer.Deserialize<SavedSettings>(File.ReadAllText(path));
        if (saved is not null) { defaults.ExecutablePath = saved.PythonExecutable; defaults.Device = saved.Device; defaults.PoseModel=saved.PoseModel; defaults.PoseWeights=saved.PoseWeights; defaults.CropPadding=saved.CropPadding; defaults.Correction=saved.Correction ?? new(); }
        if (saved?.VisionExecutablePath is {} vision) defaults.VisionExecutablePath = vision;
        if (saved?.SamuraiExecutablePath is {} samurai) defaults.SamuraiExecutablePath = samurai;
        if (saved?.PointsExecutablePath is {} points) defaults.PointsExecutablePath = points;
        if (saved?.SamuraiModelsRoot is {} samuraiRoot) defaults.SamuraiModelsRoot = samuraiRoot;
        if (saved?.PointsModelsRoot is {} pointsRoot) defaults.PointsModelsRoot = pointsRoot;
        if (saved is not null)
        {
            defaults.TapNextResolution = saved.TapNextResolution;
            defaults.TapNextCheckpoint = saved.TapNextCheckpoint ?? "";
        }
        if (!string.IsNullOrWhiteSpace(saved?.ModelsRoot))
        {
            var oldDefault = FindInstalledModelsRoot(Environment.GetEnvironmentVariable("LOCALAPPDATA"),
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData));
            // Migrate only the unavailable former default, never an explicit custom location.
            if (File.Exists(Path.Combine(saved.ModelsRoot, "manifest.json")) ||
                !string.Equals(Path.TrimEndingDirectorySeparator(saved.ModelsRoot), oldDefault, StringComparison.OrdinalIgnoreCase))
                defaults.ModelsRoot = saved.ModelsRoot;
        }
        if (saved?.BarbellProvider is {} provider) defaults.BarbellProvider = provider;
        return defaults;
    }

    public async Task SaveAsync(CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(DataDirectory);
        var path = Path.Combine(DataDirectory, "settings.json");
        var temporary = path + ".tmp";
        await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(new SavedSettings(ExecutablePath, Device, PoseModel, PoseWeights, CropPadding, Correction, VisionExecutablePath, ModelsRoot, BarbellProvider,
            SamuraiExecutablePath, PointsExecutablePath, SamuraiModelsRoot, PointsModelsRoot, TapNextResolution, TapNextCheckpoint)), cancellationToken);
        File.Move(temporary, path, true);
    }

    private sealed record SavedSettings(string PythonExecutable, string Device, string PoseModel="rtmpose-l_8xb256-420e_body8-384x288", string PoseWeights="", double CropPadding=.2, MotionTrace.Core.PoseCorrection.PoseCorrectionOptions? Correction=null,
        string? VisionExecutablePath=null, string? ModelsRoot=null, string? BarbellProvider=null,
        string? SamuraiExecutablePath=null, string? PointsExecutablePath=null, string? SamuraiModelsRoot=null, string? PointsModelsRoot=null,
        int TapNextResolution=256, string? TapNextCheckpoint=null);
}
