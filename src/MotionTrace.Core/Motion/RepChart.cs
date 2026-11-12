namespace MotionTrace.Core.Motion;

public enum MotionChartMetric { Velocity, Height }
public enum MotionChartAxis { Time, Rom }

/// <summary>Selection is independent from the rep explicitly activated for playback.</summary>
public sealed class RepSelectionState
{
    private readonly HashSet<int> selected=[];
    private readonly HashSet<int> available=[];
    public IReadOnlySet<int> Selected => selected;
    public int? ActiveRep { get; private set; }
    public void Reset(IEnumerable<int> ids) { available.Clear();available.UnionWith(ids);Clear(); }
    public void Activate(int id) { if(!available.Contains(id))return;selected.Clear();selected.Add(id);ActiveRep=id; }
    public void Toggle(int id) { if(!available.Contains(id))return;if(!selected.Add(id))selected.Remove(id);if(ActiveRep is null || !selected.Contains(ActiveRep.Value))ActiveRep=selected.Order().Select(x=>(int?)x).FirstOrDefault(); }
    public void SelectAll() { selected.UnionWith(available);ActiveRep ??=selected.Order().Select(x=>(int?)x).FirstOrDefault(); }
    public void Clear() { selected.Clear();ActiveRep=null; }
}

public readonly record struct MotionChartSample(double X,double Y,double Timestamp,int Segment);

/// <summary>A projection over existing analysis samples. No retained copy of the trajectory.</summary>
public sealed record MotionChartSeries(string SourceVideoId,string RepId,string DisplayName,
    IReadOnlyList<MovementPoint> Samples,double Start,double End,double HeightOrigin,
    MotionChartMetric Metric,MotionChartAxis Axis,double RomBottom=0,double RomTop=0)
{
    public double? TimeOrigin { get; init; }
    public double ValueScale { get; init; } = 1;
    public int? PaletteIndex { get; init; }
    public int VisiblePhases {get;init;}=15;
    public bool LoweringFollowsLifting {get;init;}
    public double? LiftingEnd {get;init;}
    public int PhaseAt(double time)=>LoweringFollowsLifting?(time<LiftingStart?0:time<LiftingEnd?3:time<LoweringStart?2:1):LiftingStart is null?3:LoweringStart is not null && time<LoweringStart?0:time>=LiftingStart?3:LoweringEnd is not null && time>=LoweringEnd?2:1;
    public bool VisibleAt(double time)=>(VisiblePhases & (1<<PhaseAt(time)))!=0;
    public double? LoweringStart { get; init; }
    public double? LoweringEnd { get; init; }
    public double? LiftingStart { get; init; }
    public string Id => $"{SourceVideoId}/{RepId}";
    public bool HasRom => RomBottom-RomTop>1;
    public MotionChartSample Project(MovementPoint point) => new(
        Axis==MotionChartAxis.Rom ? Math.Clamp(100*(RomBottom-point.Y)/(RomBottom-RomTop),0,100) : point.Time-(TimeOrigin ?? Start),
        (Metric==MotionChartMetric.Velocity ? -point.Velocity : HeightOrigin-point.Y)*ValueScale,point.Time,point.Segment);
    public IEnumerable<MotionChartSample> Points => Samples.Where(p=>p.Time>=Start && p.Time<=End)
        .Where(p=>VisibleAt(p.Time)).Where(_=>Axis!=MotionChartAxis.Rom || HasRom).Select(p=>Project(p) with {Segment=p.Segment*4+PhaseAt(p.Time)});
    public double? TimestampAtX(double x,double referenceTime)
    {
        if(!double.IsFinite(x))return null;
        if(Axis==MotionChartAxis.Time) {double t=Math.Clamp((TimeOrigin ?? Start)+x,Start,End);return VisibleAt(t)?t:Points.OrderBy(p=>Math.Abs(p.Timestamp-t)).Select(p=>(double?)p.Timestamp).FirstOrDefault();}
        // ROM can cross the same height more than once: choose the closest sample,
        // breaking ties with the current playback time rather than jumping arbitrarily.
        if(!HasRom)return null;
        return Points.OrderBy(p=>Math.Abs(p.X-x)).ThenBy(p=>Math.Abs(p.Timestamp-referenceTime)).Select(p=>(double?)p.Timestamp).FirstOrDefault();
    }
    public MotionChartSample? At(double timestamp)
    {
        // MediaPlayer rounds Position to 100 ns; tolerate only that numerical boundary error.
        if(!VisibleAt(timestamp) || timestamp<Start-1e-6 || timestamp>End+1e-6 || (Axis==MotionChartAxis.Rom && !HasRom))return null;
        timestamp=Math.Clamp(timestamp,Start,End);
        var p=PlaybackSampleLookup.At(Samples,timestamp);
        return p is null?null:Project(p);
    }
}

public static class RepChartData
{
    public static IReadOnlyList<MotionChartSeries> Create(string videoId,MovementAnalysis analysis,
        IReadOnlySet<int> selected,MotionChartMetric metric,MotionChartAxis axis)
    {
        if(analysis.Reps.Count==0 && analysis.Points.Count>1 && axis==MotionChartAxis.Time)
            return [new(videoId,"trajectory","Full movement · no complete rep",analysis.Points,analysis.Points[0].Time,analysis.Points[^1].Time,analysis.Points[0].Y,metric,axis)];
        var reps=analysis.Reps.Where(r=>selected.Contains(r.Number));
        return reps.Select(rep=> {
            bool rom=axis==MotionChartAxis.Rom;
            var lifting=rep.Lifting;
            return new MotionChartSeries(videoId,rep.Number.ToString(),$"Rep {rep.Number}",
                rom?lifting.Points:analysis.Points,rom?lifting.Start:rep.PreparationStart ?? rep.Start,rom?lifting.End:rep.End,
                lifting.Points[0].Y,metric,axis,lifting.Points[0].Y,lifting.Points[^1].Y) { LoweringFollowsLifting=rep.LoweringFollowsLifting,LiftingEnd=lifting.End,LoweringStart=rep.Lowering?.Start,LoweringEnd=rep.Lowering?.End,LiftingStart=lifting.Start };
        }).ToArray();
    }
}

public static class RepMetricsPresenter
{
    public static string Describe(IReadOnlyList<MovementRep> reps,string source="Wrist")
    {
        if(reps.Count==0)return "Select a rep to inspect its movement.";
        return string.Join("\n\n",reps.Select(r =>
            $"Rep {r.Number} · {r.Quality}\nLowering  {(r.Lowering is null?"—":$"{r.Lowering.Duration:0.00} s")}    Lifting  {r.Lifting.Duration:0.00} s\nTotal  {r.Duration:0.00} s    Pause  {r.PauseSeconds:0.00} s\nMax lifting speed  {r.Lifting.PeakSpeed:0.0} px/s\nMean  {r.Lifting.MeanSpeed:0.0} px/s · {source} estimate"));
    }
}
