using MotionTrace.Infrastructure.AI;

namespace MotionTrace.Tests;

public sealed class BarbellProviderSettingsTests
{
    [Theory]
    [InlineData("custom_barbell")]
    [InlineData("grounding_dino_sam2")]
    public async Task ModelSelectionIsPersistedWithoutChangingLegacyDefault(string provider)
    {
        var directory = Path.Combine(Path.GetTempPath(), "MotionTrace-provider-" + Guid.NewGuid().ToString("N"));
        try
        {
            Assert.Equal("custom_barbell", PythonOptions.Load(directory).BarbellProvider);
            var options = new PythonOptions { DataDirectory = directory, BarbellProvider = provider };
            await options.SaveAsync();
            Assert.Equal(provider, PythonOptions.Load(directory).BarbellProvider);
            var file = Path.Combine(directory, "settings.json");
            var settings = System.Text.Json.Nodes.JsonNode.Parse(await File.ReadAllTextAsync(file))!;
            settings.AsObject().Remove("BarbellProvider");
            await File.WriteAllTextAsync(file, settings.ToJsonString());
            Assert.Equal("custom_barbell", PythonOptions.Load(directory).BarbellProvider);
        }
        finally { if (Directory.Exists(directory)) Directory.Delete(directory, true); }
    }
}
