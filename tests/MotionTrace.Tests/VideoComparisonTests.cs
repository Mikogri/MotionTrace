using MotionTrace.Core.Motion;

namespace MotionTrace.Tests;

public class VideoComparisonTests
{
    private static (MovementAnalysis Analysis, MovementRep Rep) Bench(double start, double scale = 1)
    {
        MovementPoint[] points =
        [
            new(start - 2, 100 * scale, 0, 0),
            new(start, 100 * scale, 100 * scale, 0),
            new(start + 1, 200 * scale, 0, 0),
            new(start + 1.5, 200 * scale, -100 * scale, 0),
            new(start + 3, 100 * scale, 0, 0)
        ];
        var rep = new MovementRep(1, new(start, start + 1, points[1..3], false),
            new(start + 1.5, start + 3, points[3..], true)) { PreparationStart = start - 2 };
        return (new(points, [rep], ""), rep);
    }

    private static MotionChartSeries Series(MovementAnalysis analysis, string id = "A",
        MotionChartMetric metric = MotionChartMetric.Height, MotionChartAxis axis = MotionChartAxis.Time,
        bool normalize = false)
        => Assert.Single(VideoComparison.CreateSeries(id, analysis, new HashSet<int> { 1 }, metric, axis, normalize));

    [Fact]
    public void TimeAlignsMovementStartsAndPreservesNegativePreparationAndSeek()
    {
        var a = Series(Bench(5).Analysis);
        var b = Series(Bench(20).Analysis, "B");
        Assert.Equal(new double[] { -2, 0, 1, 1.5, 3 }, a.Points.Select(point => point.X));
        Assert.Equal(a.Points.Select(point => point.X), b.Points.Select(point => point.X));
        Assert.Equal(3, a.Start);
        Assert.Equal(8, a.End);
        Assert.Equal(5, a.TimeOrigin);
        Assert.Equal(4, a.TimestampAtX(-1, 0));
        Assert.Equal(21.5, b.TimestampAtX(1.5, 0));
        Assert.Equal(18, b.TimestampAtX(-20, 0));
        Assert.Equal(23, b.TimestampAtX(20, 0));
        Assert.Equal("A", a.SourceVideoId);
        Assert.Equal("B", b.SourceVideoId);
        Assert.NotEqual(a.Id, b.Id);
    }

    [Fact]
    public void ComparisonPreservesSamplesPhaseBoundariesAndSegments()
    {
        var (analysis, rep) = Bench(5);
        var series = Series(analysis);
        Assert.Same(analysis.Points, series.Samples);
        Assert.Equal(rep.Lowering!.Start, series.LoweringStart);
        Assert.Equal(rep.Lowering.End, series.LoweringEnd);
        Assert.Equal(rep.Lifting.Start, series.LiftingStart);
        Assert.Equal(rep.Lifting.End, series.LiftingEnd);
        Assert.Equal(new[] { 0, 1, 2, 3, 3 }, series.Points.Select(point => point.Segment));
        var hiddenPreparation = series with { VisiblePhases = 14 };
        Assert.Equal(0, hiddenPreparation.Points.First().X);
        Assert.Equal(5, hiddenPreparation.TimestampAtX(-1, 0));
    }

    [Theory]
    [InlineData(MotionChartMetric.Height)]
    [InlineData(MotionChartMetric.Velocity)]
    public void NormalizedValuesMatchAcrossDifferentPixelScales(MotionChartMetric metric)
    {
        var a = Series(Bench(5).Analysis, metric: metric, normalize: true);
        var b = Series(Bench(20, 2).Analysis, "B", metric, normalize: true);
        Assert.Equal(a.Points.Select(point => point.Y), b.Points.Select(point => point.Y));
        Assert.Equal(1, a.ValueScale);
        Assert.Equal(.5, b.ValueScale);
        var raw = Series(Bench(20, 2).Analysis, metric: metric);
        Assert.Equal(raw.Points.Select(point => point.Y / 2), b.Points.Select(point => point.Y));
    }

    [Fact]
    public void RomAxisStillUsesLiftingDisplacementAndOnlyLiftingSamples()
    {
        var (analysis, rep) = Bench(20);
        var series = Series(analysis, axis: MotionChartAxis.Rom, normalize: true);
        Assert.Same(rep.Lifting.Points, series.Samples);
        Assert.Equal(new double[] { 0, 100 }, series.Points.Select(point => point.X));
        Assert.Equal(rep.Lifting.Start, series.TimestampAtX(0, rep.Start));
        Assert.Equal(rep.Lifting.End, series.TimestampAtX(100, rep.Start));
    }

    [Fact]
    public void ZeroRomOmitsNormalizedSeriesAndSpeedsButRetainsRawData()
    {
        var (analysis, rep) = Bench(5, 0);
        Assert.Empty(VideoComparison.CreateSeries("A", analysis, new HashSet<int> { 1 },
            MotionChartMetric.Height, MotionChartAxis.Time, true));
        Assert.NotEmpty(Series(analysis).Points);
        Assert.All(VideoComparison.Compare(rep, rep).Where(row => row.Unit == "%ROM/s"), row =>
        {
            Assert.Null(row.A);
            Assert.Null(row.B);
            Assert.Null(row.Difference);
            Assert.Null(row.DifferencePercent);
        });
    }

    [Fact]
    public void MissingDeadliftLoweringIsAbsentAndReturnUsesTopPause()
    {
        MovementPoint[] points = [new(3, 200, -100, 0), new(4, 100, 0, 0)];
        var first = new MovementRep(1, null, new(3, 4, points, true));
        var returned = first with { Lowering = new(4.5, 5.5, [new(4.5, 100, 100, 0), new(5.5, 200, 0, 0)], false) };
        var rows = VideoComparison.Compare(first, returned).ToDictionary(row => row.Key);
        Assert.Null(rows["lowering"].A);
        Assert.Equal(1, rows["lowering"].B);
        Assert.Null(rows["lowering-mean-normalized"].A);
        Assert.Null(rows["bottom-pause"].A);
        Assert.Null(rows["bottom-pause"].B);
        Assert.Null(rows["top-pause"].A);
        Assert.Equal(.5, rows["top-pause"].B);
        Assert.Null(rows["preparation"].A);
        Assert.Null(rows["lowering"].Difference);
    }

    [Fact]
    public void MetricsExposeSignedDifferenceAndPercentOnlyWithNonzeroBaseline()
    {
        var rows = VideoComparison.Compare(Bench(5).Rep, Bench(20, 2).Rep).ToDictionary(row => row.Key);
        Assert.Equal(100, rows["rom"].Difference);
        Assert.Equal(100, rows["rom"].DifferencePercent);
        Assert.Equal(0, rows["lifting-mean-normalized"].Difference);
        Assert.Equal(-1, new VideoComparisonMetric("x", "x", "s", 2, 1).Difference);
        Assert.Equal(-50, new VideoComparisonMetric("x", "x", "s", 2, 1).DifferencePercent);
        Assert.Null(new VideoComparisonMetric("x", "x", "s", 0, 1).DifferencePercent);
        Assert.All(VideoComparison.Compare(null, null), row => Assert.Null(row.Difference));
    }

    [Fact]
    public void SelectionDoesNotInventARepForAnUnclassifiedTrajectory()
    {
        var (analysis, _) = Bench(5);
        Assert.Empty(VideoComparison.CreateSeries("A", analysis, new HashSet<int> { 99 },
            MotionChartMetric.Height, MotionChartAxis.Time, false));
        Assert.Empty(VideoComparison.CreateSeries("A", analysis with { Reps = [] }, new HashSet<int>(),
            MotionChartMetric.Height, MotionChartAxis.Time, false));
    }
}
