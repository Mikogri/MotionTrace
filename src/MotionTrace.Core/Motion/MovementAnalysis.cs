using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;

namespace MotionTrace.Core.Motion;

public sealed record MovementPoint(double Time, double Y, double Velocity, int Segment)
{
    public int FrameIndex { get; init; } = -1;
    public double Confidence { get; init; } = 1;
    public AnalysisQuality Quality { get; init; }
    public double RawY { get; init; }
    public string? ObjectId { get; init; }
    public string? Source { get; init; }
    public bool IsProxy { get; init; }
    public bool IsInterpolated { get; init; }
    public bool IsManualCorrection { get; init; }
}
public sealed record MovementPhase(double Start, double End, IReadOnlyList<MovementPoint> Points, bool Upward)
{
    public double Duration => End - Start;
    public double MeanSpeed => Points.Count < 2 ? 0 : Math.Abs(Points[^1].Y - Points[0].Y) / Duration;
    public double PeakSpeed => Points.Count == 0 ? 0 : Points.Max(p => Math.Max(0, Upward ? -p.Velocity : p.Velocity));
}
public sealed record MovementRep(int Number, MovementPhase? Lowering, MovementPhase Lifting)
{
    public double? PreparationStart { get; init; }
    public double PreparationSeconds => Math.Max(0,Start-(PreparationStart ?? Start));
    public bool LoweringFollowsLifting => Lowering is not null && Lowering.Start>=Lifting.End;
    public double Start => LoweringFollowsLifting?Lifting.Start:Lowering?.Start ?? Lifting.Start;
    public double End => LoweringFollowsLifting?Lowering!.End:Lifting.End;
    public double PauseSeconds => Lowering is null ? 0 : LoweringFollowsLifting?Math.Max(0,Lowering.Start-Lifting.End):Math.Max(0, Lifting.Start - Lowering.End);
    public double Duration => End - Start;
    public AnalysisQuality Quality => (AnalysisQuality)(Lowering?.Points.Concat(Lifting.Points) ?? Lifting.Points).Select(p=>(int)p.Quality).DefaultIfEmpty((int)AnalysisQuality.Poor).Max();
    public int StartFrame => (LoweringFollowsLifting?Lifting:Lowering ?? Lifting).Points[0].FrameIndex;
    public int EndFrame => (LoweringFollowsLifting?Lowering!:Lifting).Points[^1].FrameIndex;
    public string Label => $"Rep {Number} · {Duration:0.00} s · {Quality}";
}
public sealed record MovementAnalysis(IReadOnlyList<MovementPoint> Points, IReadOnlyList<MovementRep> Reps, string Note)
{
    public string MeasurementSource { get; init; } = "Wrist";
}

/// <summary>Image-space wrist motion, not bar tracking. Each gap is an independent segment.</summary>
public static class MovementAnalyzer
{
    public static MovementAnalysis Analyze(IReadOnlyList<PoseFrame> frames, int athleteId, Joint wrist,
        ExerciseType exercise, int frameHeight, double minimumTravelPercent = 1.5, CancellationToken token = default)
    {
        return AnalyzeTrajectory(new WristTrajectoryProvider().Extract(frames,athleteId,wrist,token),exercise,frameHeight,minimumTravelPercent,token);
    }

    public static MovementAnalysis AnalyzeSignal(IReadOnlyList<BarbellSample> samples, ExerciseType exercise,
        int frameHeight, double minimumTravelPercent = 1.5, CancellationToken token = default)
        => AnalyzeTrajectory(samples.Select((s,i)=>new MotionSample(i,s.TimestampSeconds,s.Position,s.Position,s.Confidence,AnalysisQuality.Good)).ToArray(),exercise,frameHeight,minimumTravelPercent,token);

    public static MovementAnalysis AnalyzeTrajectory(IReadOnlyList<MotionSample> samples, ExerciseType exercise,
        int frameHeight,double minimumTravelPercent=1.5,CancellationToken token=default)
    {
        if (frameHeight <= 0 || !double.IsFinite(minimumTravelPercent) || minimumTravelPercent is < .2 or > 10)
            throw new ArgumentOutOfRangeException(nameof(minimumTravelPercent));
        if (exercise is not (ExerciseType.BenchPress or ExerciseType.Squat or ExerciseType.Deadlift))
            throw new ArgumentException("Choose an exercise explicitly.", nameof(exercise));
        var rawSegments = new List<List<MotionSample>>();
        var current = new List<MotionSample>();
        double previousTime = -1;
        foreach (var sample in MotionGapRepair.FillShortGaps(samples,frameHeight))
        {
            token.ThrowIfCancellationRequested();
            if (!double.IsFinite(sample.TimestampSeconds) || sample.TimestampSeconds < 0 || sample.TimestampSeconds <= previousTime)
                throw new ArgumentException("Timestamps must be finite and strictly increasing.");
            previousTime = sample.TimestampSeconds;
            bool valid = double.IsFinite(sample.Position.Y) && double.IsFinite(sample.Position.X) &&
                double.IsFinite(sample.Confidence) && sample.Confidence is >= .4 and <= 1;
            if (!valid || (current.Count > 0 && (sample.ContinuityId!=current[^1].ContinuityId || sample.TimestampSeconds - current[^1].TimestampSeconds > .25 ||
                Math.Abs(sample.Position.Y-current[^1].Position.Y) > frameHeight * .12)))
            {
                if (current.Count > 0) rawSegments.Add(current);
                current = [];
            }
            if (valid) current.Add(sample);
        }
        if (current.Count > 0) rawSegments.Add(current);
        var points = new List<MovementPoint>();
        var reps = new List<MovementRep>();
        double travel = frameHeight * minimumTravelPercent / 100;
        for (int segment = 0; segment < rawSegments.Count; segment++)
        {
            token.ThrowIfCancellationRequested();
            var raw = rawSegments[segment];
            // Time-based smoothing preserves the meaning of seconds for variable-rate footage.
            var median = new double[raw.Count];
            for (int i = 0; i < raw.Count; i++)
            {
                token.ThrowIfCancellationRequested();
                var neighborhood = new List<double>();
                for (int j=i; j>=0 && raw[i].TimestampSeconds-raw[j].TimestampSeconds<=.075; j--) neighborhood.Add(raw[j].Position.Y);
                for (int j=i+1; j<raw.Count && raw[j].TimestampSeconds-raw[i].TimestampSeconds<=.075; j++) neighborhood.Add(raw[j].Position.Y);
                neighborhood.Sort(); median[i]=neighborhood[neighborhood.Count/2];
            }
            if (raw.All(sample => sample.Source == "tapnextpp-midpoint"))
            {
                // A small image-space deadband suppresses point-tracker shimmer before
                // differentiation. Keep raw coordinates, and reset at every visibility gap.
                // Compare against the held position, so genuine slow movement accumulates.
                double held = median[0], tolerance = Math.Max(.25, frameHeight * .001);
                for (int i = 1; i < median.Length; i++)
                {
                    if (Math.Abs(median[i] - held) > tolerance) held = median[i];
                    median[i] = held;
                }
            }
            var smooth = new List<MovementPoint>();
            for (int i=0; i<raw.Count; i++)
            {
                int a=i,b=i;
                while(a>0 && raw[i].TimestampSeconds-raw[a-1].TimestampSeconds<=.1) a--;
                while(b+1<raw.Count && raw[b+1].TimestampSeconds-raw[i].TimestampSeconds<=.1) b++;
                double mt=0,my=0,cov=0,var=0;
                for(int j=a;j<=b;j++) { mt+=raw[j].TimestampSeconds; my+=median[j]; }
                mt/=b-a+1; my/=b-a+1;
                for(int j=a;j<=b;j++) { double dt=raw[j].TimestampSeconds-mt; cov+=dt*(median[j]-my); var+=dt*dt; }
                smooth.Add(new(raw[i].TimestampSeconds,median[i],var>0?cov/var:0,segment) {FrameIndex=raw[i].FrameIndex,RawY=raw[i].RawPosition.Y,Confidence=raw[i].Confidence,Quality=raw[i].Quality,
                    ObjectId=raw[i].ObjectId,Source=raw[i].Source,IsProxy=raw[i].IsProxy,IsInterpolated=raw[i].IsInterpolated,IsManualCorrection=raw[i].IsManualCorrection});
            }
            points.AddRange(smooth);
            MovementRepDetector.Detect(smooth, exercise, travel, reps, token);
        }
        return new(points, reps, "Wrist estimate · vertical px/s, not barbell m/s. Camera motion, setup and occlusion can create false or missed reps. Gaps and incomplete reps are excluded.");
    }

}
