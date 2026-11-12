using MotionTrace.Core.Athletes;

namespace MotionTrace.Core.Motion;

public sealed record BarbellSample(double TimestampSeconds, Point2 Position, double Confidence);
public sealed record BarbellTrackingResult(bool IsAvailable, IReadOnlyList<BarbellSample> Samples, string Limitation);
public interface IBarbellTracker
{
    Task<BarbellTrackingResult> TrackAsync(string videoPath, CancellationToken cancellationToken);
}
public sealed class UnavailableBarbellTracker : IBarbellTracker
{
    public Task<BarbellTrackingResult> TrackAsync(string videoPath, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(new BarbellTrackingResult(false, [], "No barbell detector is configured. RTMPose detects body joints only."));
    }
}
public sealed record VelocitySample(double TimestampSeconds, double VelocityX, double VelocityY)
{
    public double Speed => Math.Sqrt(VelocityX * VelocityX + VelocityY * VelocityY);
}
public sealed record VelocitySeries(string Unit, IReadOnlyList<VelocitySample> Samples);

public static class VelocityCalculator
{
    public static VelocitySeries Calculate(IReadOnlyList<BarbellSample> positions, double? metersPerPixel = null,
        double maximumGapSeconds = 0.25, double minimumConfidence = 0.5)
    {
        if (metersPerPixel is { } scale && (!double.IsFinite(scale) || scale <= 0)) throw new ArgumentOutOfRangeException(nameof(metersPerPixel));
        if (!double.IsFinite(maximumGapSeconds) || maximumGapSeconds <= 0 || minimumConfidence is < 0 or > 1)
            throw new ArgumentOutOfRangeException(nameof(maximumGapSeconds));
        var samples = new List<VelocitySample>();
        for (int i = 0; i < positions.Count; i++)
        {
            var current = positions[i];
            if (!double.IsFinite(current.TimestampSeconds) || current.TimestampSeconds < 0 ||
                !double.IsFinite(current.Position.X) || !double.IsFinite(current.Position.Y) ||
                !double.IsFinite(current.Confidence) || current.Confidence is < 0 or > 1)
                throw new ArgumentException("Invalid motion sample.");
            if (i == 0) continue;
            var previous = positions[i - 1];
            var dt = current.TimestampSeconds - previous.TimestampSeconds;
            if (dt <= 0) throw new ArgumentException("Timestamps must increase strictly.");
            if (dt > maximumGapSeconds || Math.Min(previous.Confidence, current.Confidence) < minimumConfidence) continue;
            var multiplier = (metersPerPixel ?? 1) / dt;
            samples.Add(new(current.TimestampSeconds, (current.Position.X - previous.Position.X) * multiplier,
                (current.Position.Y - previous.Position.Y) * multiplier));
        }
        return new(metersPerPixel.HasValue ? "m/s" : "px/s", samples);
    }
}
