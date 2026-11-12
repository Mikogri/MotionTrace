using MotionTrace.Infrastructure.AI;

namespace MotionTrace.Tests;

public sealed class VisionModelPathTests
{
    [Fact]
    public void FindsSharedModelsFromNestedVisualStudioOutput()
    {
        var root = Path.Combine(Path.GetTempPath(), "MotionTrace-shared-test-" + Guid.NewGuid().ToString("N"));
        var models = Path.Combine(root, ".models", "vision");
        Directory.CreateDirectory(models);
        try
        {
            File.WriteAllText(Path.Combine(models, "manifest.json"), "{}");
            Assert.Equal(models, PythonOptions.FindProjectModelsRoot(Path.Combine(root, "app", "bin", "Debug")));
            Assert.Equal(models, PythonOptions.FindProjectModelsRoot(Path.Combine(root, "artifacts", "app")));
        }
        finally { Directory.Delete(root, true); }
    }

    [Fact]
    public void FindsInstallerLocationWhenHostUsesDifferentLocalDirectory()
    {
        var root = Path.Combine(Path.GetTempPath(), "MotionTrace-path-test-" + Guid.NewGuid().ToString("N"));
        var installed = Path.Combine(root, "user", "MotionTrace", "models", "vision");
        Directory.CreateDirectory(installed);
        try
        {
            File.WriteAllText(Path.Combine(installed, "manifest.json"), "{}");
            Assert.Equal(installed, PythonOptions.FindInstalledModelsRoot(Path.Combine(root, "host"), Path.Combine(root, "user")));
            Assert.Equal(installed, PythonOptions.FindInstalledModelsRoot(null, "", "relative", Path.Combine(root, "user")));
        }
        finally { Directory.Delete(root, true); }
    }
}
