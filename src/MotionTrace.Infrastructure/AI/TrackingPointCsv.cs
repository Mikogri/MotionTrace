using System.Globalization;
using System.Text.Json;
using MotionTrace.Core.Analysis;

namespace MotionTrace.Infrastructure.AI;

/// <summary>Preserves each queried point and its visibility independently of midpoint measurements.</summary>
public static class TrackingPointCsv
{
    public static void Write(TextWriter writer, AnalysisResult analysis)
    {
        writer.WriteLine("timestamp_s,frame_index,athlete_id,point_index,object_id,visible,raw_x_px,raw_y_px,visibility_probability,measurement_available,x_px,y_px");
        for (int index = 0; index < analysis.Frames.Count; index++)
        {
            var frame = analysis.Frames[index];
            foreach (var point in frame.Objects.Where(o => o.PointIndex is not null))
            {
                using var raw = point.RawObservationJson is {} json ? JsonDocument.Parse(json) : null;
                var root = raw?.RootElement;
                string Number(string name) => root is {} r && r.TryGetProperty(name, out var value) &&
                    value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var n) && double.IsFinite(n) ? N(n) : "";
                bool visible = root is {} element && element.TryGetProperty("visible", out var visibility) && visibility.ValueKind == JsonValueKind.True;
                var measurement = point.Measurement;
                writer.WriteLine(string.Join(",", N(frame.TimestampSeconds), index.ToString(CultureInfo.InvariantCulture),
                    point.AthleteId?.ToString(CultureInfo.InvariantCulture), point.PointIndex?.ToString(CultureInfo.InvariantCulture),
                    "\"" + point.ObjectId.Replace("\"", "\"\"") + "\"", visible, Number("x"), Number("y"),
                    Number("visibilityProbability"), measurement is not null,
                    measurement is null ? "" : N(measurement.Position.X), measurement is null ? "" : N(measurement.Position.Y)));
            }
        }
    }

    private static string N(double value) => value.ToString("G17", CultureInfo.InvariantCulture);
}
