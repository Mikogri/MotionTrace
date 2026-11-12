using MotionTrace.Core.Analysis;
using Windows.Storage;

namespace motion_trace_win.Features.VideoImport;

public sealed class VideoImportService
{
    private const string FrameRateProperty = "System.Video.FrameRate";
    public static readonly string[] Extensions = [".mp4", ".mov", ".avi"];
    public async Task<VideoMetadata> ReadAsync(string path, CancellationToken cancellationToken)
    {
        if (!Extensions.Contains(Path.GetExtension(path), StringComparer.OrdinalIgnoreCase))
            throw new InvalidOperationException("Select an MP4, MOV or AVI video.");
        cancellationToken.ThrowIfCancellationRequested();
        var file = await StorageFile.GetFileFromPathAsync(path).AsTask(cancellationToken);
        var properties = await file.Properties.GetVideoPropertiesAsync().AsTask(cancellationToken);
        if (properties.Width == 0 || properties.Height == 0 || properties.Duration <= TimeSpan.Zero)
            throw new InvalidOperationException("Windows cannot read this video. Check that its codec is installed.");
        var extended = await file.Properties.RetrievePropertiesAsync([FrameRateProperty]).AsTask(cancellationToken);
        double fps = extended.TryGetValue(FrameRateProperty, out var value) && value is not null ? Convert.ToDouble(value) / 1000.0 : 0;
        var size = VideoCoordinates.DisplaySize((int)properties.Width, (int)properties.Height, (int)properties.Orientation);
        return new(file.Name, properties.Duration.TotalSeconds, size.Width, size.Height, fps);
    }
}
