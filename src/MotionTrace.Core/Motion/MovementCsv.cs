using System.Globalization;
using System.Text;
namespace MotionTrace.Core.Motion;

public static class MovementCsv
{
    private static string N(double value)=>value.ToString("G17",CultureInfo.InvariantCulture);
    private static string Q(string value)=>"\""+value.Replace("\"","\"\"")+"\"";
    public static void WriteSamples(TextWriter writer,MovementAnalysis analysis)
    {
        writer.WriteLine("timestamp_s,frame_index,segment,source,rep,phase,position_y_px,raw_y_px,upward_velocity_px_s,confidence,quality,object_id,is_proxy,is_interpolated,is_manual_correction");
        foreach(var p in analysis.Points) {
            var rep=analysis.Reps.FirstOrDefault(r=>p.Time>=(r.PreparationStart??r.Start) && p.Time<=r.End);
            string phase=rep is null?"unclassified":p.Time<rep.Start?"preparation":rep.LoweringFollowsLifting?(p.Time<rep.Lifting.End?"lifting":p.Time<rep.Lowering!.Start?"top_pause":"lowering"):rep.Lowering is not null && p.Time<rep.Lowering.End?"lowering":p.Time<rep.Lifting.Start?"bottom_pause":"lifting";
            writer.WriteLine(string.Join(",",N(p.Time),p.FrameIndex.ToString(CultureInfo.InvariantCulture),p.Segment.ToString(CultureInfo.InvariantCulture),Q(p.Source ?? analysis.MeasurementSource),rep?.Number.ToString(CultureInfo.InvariantCulture)??"",phase,N(p.Y),N(p.RawY),N(-p.Velocity),N(p.Confidence),p.Quality.ToString(),Q(p.ObjectId ?? ""),p.IsProxy,p.IsInterpolated,p.IsManualCorrection));
        }
    }
    public static void WriteReps(TextWriter writer,MovementAnalysis analysis)
    {
        writer.WriteLine("rep,source,preparation_start_s,lowering_start_s,lowering_end_s,lifting_start_s,end_s,preparation_s,lowering_s,bottom_pause_s,lifting_s,lift_total_s,total_with_preparation_s,max_lifting_speed_px_s,top_pause_s,lifting_end_s");
        foreach(var r in analysis.Reps)
            writer.WriteLine(string.Join(",",r.Number.ToString(CultureInfo.InvariantCulture),Q(analysis.MeasurementSource),r.PreparationStart is {} prep?N(prep):"",r.Lowering is {} down?N(down.Start):"",r.Lowering is {} lowering?N(lowering.End):"",N(r.Lifting.Start),N(r.End),r.PreparationStart is null?"":N(r.PreparationSeconds),r.Lowering is null?"":N(r.Lowering.Duration),r.Lowering is null || r.LoweringFollowsLifting?"":N(r.PauseSeconds),N(r.Lifting.Duration),N(r.Duration),N(r.Duration+r.PreparationSeconds),N(r.Lifting.PeakSpeed),r.LoweringFollowsLifting?N(r.PauseSeconds):"",N(r.Lifting.End)));
    }
}
