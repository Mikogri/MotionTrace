using MotionTrace.Core.Motion;

namespace MotionTrace.Tests;

public class VelocityTests
{
    [Fact] public void UncalibratedVelocityUsesBothPixelAxes()
    {
        var series = VelocityCalculator.Calculate([new(0, new(10, 20), 1), new(0.1, new(13, 24), 1)]);
        Assert.Equal("px/s", series.Unit);
        Assert.Equal(30, series.Samples[0].VelocityX, 6);
        Assert.Equal(40, series.Samples[0].VelocityY, 6);
        Assert.Equal(50, series.Samples[0].Speed, 6);
    }
    [Fact] public void CalibrationConvertsUnits()
    {
        var result = VelocityCalculator.Calculate([new(0, new(0, 0), 1), new(0.1, new(10, 0), 1)], 0.01);
        Assert.Equal("m/s", result.Unit); Assert.Equal(1, result.Samples[0].Speed, 6);
    }
    [Fact] public void DoesNotBridgeGapsOrLowConfidence()
    {
        var result = VelocityCalculator.Calculate([new(0, new(0, 0), 1), new(1, new(5, 5), 1), new(1.1, new(8, 8), 0.1)]);
        Assert.Empty(result.Samples);
    }
    [Fact] public void DuplicateTimestampsAreRejected() => Assert.Throws<ArgumentException>(() =>
        VelocityCalculator.Calculate([new(1, new(0, 0), 1), new(1, new(1, 0), 1)]));
    [Fact] public void InvalidCalibrationIsRejected() => Assert.Throws<ArgumentOutOfRangeException>(() => VelocityCalculator.Calculate([], 0));
}
