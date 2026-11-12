namespace MotionTrace.Infrastructure.Logging;

public sealed class AppLog
{
    private readonly object gate = new();
    public string DirectoryPath { get; } = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MotionTrace", "logs");

    public void Write(string message)
    {
        try
        {
            lock (gate)
            {
                Directory.CreateDirectory(DirectoryPath);
                File.AppendAllText(Path.Combine(DirectoryPath, $"{DateTime.Today:yyyy-MM-dd}.log"), $"{DateTimeOffset.Now:O} {message}{Environment.NewLine}");
            }
        }
        catch (IOException) { System.Diagnostics.Debug.WriteLine(message); }
        catch (UnauthorizedAccessException) { System.Diagnostics.Debug.WriteLine(message); }
    }
}
