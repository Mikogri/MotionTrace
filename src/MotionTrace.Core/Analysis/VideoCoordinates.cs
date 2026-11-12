using MotionTrace.Core.Athletes;

namespace MotionTrace.Core.Analysis;

public static class VideoCoordinates
{
    public static (int Width, int Height) DisplaySize(int width, int height, int rotationDegrees) =>
        Math.Abs(rotationDegrees % 180) == 90 ? (height, width) : (width, height);

    /// <summary>Inverse of the player's Uniform transform. Letterbox clicks are not image coordinates.</summary>
    public static Point2? FromViewport(Point2 point, double viewportWidth, double viewportHeight, int imageWidth, int imageHeight)
    {
        if (viewportWidth <= 0 || viewportHeight <= 0 || imageWidth <= 0 || imageHeight <= 0) return null;
        double scale = Math.Min(viewportWidth / imageWidth, viewportHeight / imageHeight);
        double x = (point.X - (viewportWidth - imageWidth * scale) / 2) / scale;
        double y = (point.Y - (viewportHeight - imageHeight * scale) / 2) / scale;
        return double.IsFinite(x) && double.IsFinite(y) && x >= 0 && y >= 0 && x <= imageWidth && y <= imageHeight
            ? new(x, y) : null;
    }
}
