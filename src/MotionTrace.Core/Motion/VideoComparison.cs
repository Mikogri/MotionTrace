namespace MotionTrace.Core.Motion;

public sealed record VideoComparisonMetric(string Key, string Label, string Unit, double? A, double? B)
{
    public double? Difference => A is { } a && B is { } b ? b - a : null;
    public double? DifferencePercent => A is { } a && a != 0 && Difference is { } difference
        ? 100 * difference / Math.Abs(a) : null;
}

/// <summary>Compares existing measurements without changing tracking, phases or sample timestamps.</summary>
public static class VideoComparison
{
    public static IReadOnlyList<MotionChartSeries> CreateSeries(string videoId, MovementAnalysis analysis,
        IReadOnlySet<int> selectedRepIds, MotionChartMetric metric, MotionChartAxis axis, bool normalizeRom)
    {
        if (analysis.Reps.Count == 0) return [];
        var reps = analysis.Reps.ToDictionary(rep => rep.Number.ToString());
        return RepChartData.Create(videoId, analysis, selectedRepIds, metric, axis)
            .Where(series => !normalizeRom || series.HasRom)
            .Select(series => series with
            {
                TimeOrigin = reps[series.RepId].Start,
                ValueScale = normalizeRom ? 100 / (series.RomBottom - series.RomTop) : 1
            }).ToArray();
    }

    public static IReadOnlyList<VideoComparisonMetric> Compare(MovementRep? a, MovementRep? b)
    {
        return
        [
            Row("preparation", "Preparation", "s", rep => rep.PreparationStart is null ? null : rep.PreparationSeconds),
            Row("lowering", "Lowering", "s", rep => rep.Lowering?.Duration),
            Row("bottom-pause", "Bottom pause", "s", rep => rep.Lowering is null || rep.LoweringFollowsLifting ? null : rep.PauseSeconds),
            Row("top-pause", "Top pause", "s", rep => rep.LoweringFollowsLifting ? rep.PauseSeconds : null),
            Row("lifting", "Lifting", "s", rep => rep.Lifting.Duration),
            Row("total", "Total", "s", rep => rep.Duration),
            Row("total-with-preparation", "Total + preparation", "s", rep => rep.PreparationStart is null ? null : rep.Duration + rep.PreparationSeconds),
            Row("lowering-mean", "Mean lowering speed", "px/s", rep => rep.Lowering?.MeanSpeed),
            Row("lowering-peak", "Peak lowering speed", "px/s", rep => rep.Lowering?.PeakSpeed),
            Row("lifting-mean", "Mean lifting speed", "px/s", rep => rep.Lifting.MeanSpeed),
            Row("lifting-peak", "Peak lifting speed", "px/s", rep => rep.Lifting.PeakSpeed),
            Row("rom", "Lifting ROM", "px", Rom),
            Row("lowering-mean-normalized", "Mean lowering speed", "%ROM/s", rep => Normalize(rep, rep.Lowering?.MeanSpeed)),
            Row("lowering-peak-normalized", "Peak lowering speed", "%ROM/s", rep => Normalize(rep, rep.Lowering?.PeakSpeed)),
            Row("lifting-mean-normalized", "Mean lifting speed", "%ROM/s", rep => Normalize(rep, rep.Lifting.MeanSpeed)),
            Row("lifting-peak-normalized", "Peak lifting speed", "%ROM/s", rep => Normalize(rep, rep.Lifting.PeakSpeed))
        ];

        VideoComparisonMetric Row(string key, string label, string unit, Func<MovementRep, double?> value)
            => new(key, label, unit, a is null ? null : Finite(value(a)), b is null ? null : Finite(value(b)));
    }

    private static double? Rom(MovementRep rep) => rep.Lifting.Points.Count < 2 ? null
        : Finite(rep.Lifting.Points[0].Y - rep.Lifting.Points[^1].Y);

    private static double? Normalize(MovementRep rep, double? speed)
        => Rom(rep) is { } rom && rom > 1 && speed is { } value ? Finite(100 * value / rom) : null;

    private static double? Finite(double? value) => value is { } number && double.IsFinite(number) ? number : null;
}
