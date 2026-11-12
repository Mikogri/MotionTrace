using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;

namespace MotionTrace.Core.Motion;

/// <summary>Uses explicit measurement points, never bbox or mask centroids fabricated by the UI.</summary>
public sealed class ObjectTrajectoryProvider : IMotionTrajectoryProvider
{
    public IReadOnlyList<MotionSample> Extract(IReadOnlyList<PoseFrame> frames, int athleteId, Joint joint,
        CancellationToken token = default)
    {
        var samples = new List<MotionSample>();
        string? previousObject = null, previousSource = null;
        double previousTime = -1;
        int continuity = 0;
        for (int index = 0; index < frames.Count; index++)
        {
            token.ThrowIfCancellationRequested();
            var frame = frames[index];
            var allOwned = frame.Objects.Where(o => o.AthleteId == athleteId).ToArray();
            var owned = allOwned.Where(o => o.TrackingState == TrackingState.Tracked && o.Measurement is not null).ToArray();
            // Multiple objects for one owner are ambiguous. Never alternate between their points.
            var observation = allOwned.Any(o => o.MeasurementGroupId is not null)
                ? PairMidpoint(allOwned) : owned.Length == 1 ? owned[0] : null;
            if (observation?.Measurement is not {} measurement || measurement.Quality == AnalysisQuality.Poor)
            { previousObject = null; continue; }
            if (observation.ObjectId != previousObject || measurement.Source != previousSource ||
                measurement.IsManualCorrection || frame.TimestampSeconds - previousTime > .15)
                continuity++;
            var quality = measurement.IsProxy || measurement.IsInterpolated
                ? (AnalysisQuality)Math.Max((int)measurement.Quality, (int)AnalysisQuality.Reduced) : measurement.Quality;
            samples.Add(new(index, frame.TimestampSeconds, measurement.Position, measurement.Position,
                observation.Confidence, quality) { ContinuityId = continuity, ObjectId = observation.ObjectId,
                Source = measurement.Source, IsProxy = measurement.IsProxy, IsInterpolated = measurement.IsInterpolated,
                IsManualCorrection = measurement.IsManualCorrection });
            previousObject = observation.ObjectId;
            previousSource = measurement.Source;
            previousTime = frame.TimestampSeconds;
        }
        return samples;
    }

    private static TrackedObject? PairMidpoint(TrackedObject[] points)
    {
        if (points.Length != 2 || points.Any(p => p.TrackingState != TrackingState.Tracked ||
                p.Measurement is not { Source: "tapnextpp", IsProxy: false, IsInterpolated: false } ||
                p.Measurement.Quality == AnalysisQuality.Poor) ||
            string.IsNullOrWhiteSpace(points[0].MeasurementGroupId) ||
            points[0].MeasurementGroupId != points[1].MeasurementGroupId ||
            !points.Select(p => p.PointIndex).Order().SequenceEqual(new int?[] { 0, 1 })) return null;
        var first = points[0].Measurement!;
        var second = points[1].Measurement!;
        // A missing endpoint must create a gap, never move the measurement to the other endpoint.
        return new(points[0].MeasurementGroupId!, points[0].AthleteId, null, null,
            Math.Min(points[0].Confidence, points[1].Confidence), TrackingState.Tracked,
            new(new((first.Position.X + second.Position.X) / 2, (first.Position.Y + second.Position.Y) / 2),
                "tapnextpp-midpoint", (AnalysisQuality)Math.Max((int)first.Quality, (int)second.Quality),
                false, false, first.IsManualCorrection || second.IsManualCorrection));
    }
}

public static class MeasurementSources
{
    public static IMotionTrajectoryProvider Barbell(AnalysisResult analysis) =>
        analysis.AnalysisSchemaVersion >= 4 ? new ObjectTrajectoryProvider() : new ShaftTrajectoryProvider();

    public static string BarbellLabel(AnalysisResult analysis, int athleteId)
    {
        if (analysis.AnalysisSchemaVersion < 4) return "Barbell";
        if (analysis.Frames.Any(f => f.Objects.Any(o => o.AthleteId == athleteId && o.MeasurementGroupId is not null)))
            return "Midpoint of two tracked points";
        var measurements = analysis.Frames.SelectMany(f => f.Objects).Where(o => o.AthleteId == athleteId)
            .Select(o => o.Measurement).OfType<ObjectMeasurement>().ToArray();
        if (measurements.Length == 0) return "Object point (no data)";
        return measurements.Any(m => m.IsProxy)
            ? "Object proxy (not validated shaft axis)" : "Manually seeded tracked point";
    }
}
