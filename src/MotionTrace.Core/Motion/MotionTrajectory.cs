using MotionTrace.Core.Athletes;
namespace MotionTrace.Core.Motion;

public sealed record MotionSample(int FrameIndex,double TimestampSeconds,Point2 Position,Point2 RawPosition,double Confidence,AnalysisQuality Quality)
{
    public int ContinuityId { get; init; }
    public string? ObjectId { get; init; }
    public string? Source { get; init; }
    public bool IsProxy { get; init; }
    public bool IsInterpolated { get; init; }
    public bool IsManualCorrection { get; init; }
}
public interface IMotionTrajectoryProvider
{
    IReadOnlyList<MotionSample> Extract(IReadOnlyList<PoseFrame> frames,int athleteId,Joint joint,CancellationToken token=default);
}
public sealed class WristTrajectoryProvider : IMotionTrajectoryProvider
{
    public IReadOnlyList<MotionSample> Extract(IReadOnlyList<PoseFrame> frames,int athleteId,Joint joint,CancellationToken token=default)
    {
        if(joint is not (Joint.LeftWrist or Joint.RightWrist))throw new ArgumentException("Choose a wrist.");
        var samples=new List<MotionSample>();
        for(int i=0;i<frames.Count;i++)
        {
            token.ThrowIfCancellationRequested();
            var pose=frames[i].Athletes.FirstOrDefault(p=>p.AthleteId==athleteId && p.TrackingState==TrackingState.Tracked);
            var point=pose?.Keypoints.FirstOrDefault(k=>k.Joint==joint);
            if(point is null)continue;
            // A hidden face/leg does not invalidate a visible wrist. Measurement quality
            // is joint-specific, while the complete pose retains its own quality.
            var quality=point.Confidence<.4?AnalysisQuality.Poor:
                pose!.Quality==AnalysisQuality.Good?AnalysisQuality.Good:AnalysisQuality.Reduced;
            if(point.IsInterpolated || point.IsOutlier)quality=(AnalysisQuality)Math.Max((int)quality,(int)AnalysisQuality.Reduced);
            samples.Add(new(i,frames[i].TimestampSeconds,point.Position,point.RawPosition,
                quality==AnalysisQuality.Poor?Math.Min(.25,point.Confidence):point.Confidence,quality));
        }
        return samples;
    }
}
/// <summary>Follow shared visible shaft fragments, avoiding centroid jumps when a hand hides part of the bar.</summary>
public sealed class ShaftTrajectoryProvider : IMotionTrajectoryProvider
{
    public IReadOnlyList<MotionSample> Extract(IReadOnlyList<PoseFrame> frames,int athleteId,Joint joint,CancellationToken token=default)
    {
        var observations=frames.SelectMany(f=>f.Shafts is null ? f.GetShafts() : f.Shafts.Where(s=>s.AthleteId==athleteId)).Where(s=>s.Confidence>=.5).ToArray();
        var tracks=observations.GroupBy(s=>s.TrackId).Where(g=>athleteId<=0 ||
            g.Where(s=>s.AthleteId!=null).GroupBy(s=>s.AthleteId).OrderByDescending(v=>v.Count()).FirstOrDefault()?.Key is not {} owner || owner==athleteId).ToArray();
        var references=tracks.ToDictionary(g=>g.Key,g=>g.SelectMany(s=>s.Segments).Select(s=>(s.X1+s.X2)/2).Order().ElementAt(g.Sum(s=>s.Segments.Count)/2));
        double referenceX=references.Count==0?0:references.Values.Order().ElementAt(references.Count/2);
        int continuity=0,fragmentBridges=0;ShaftObservation? previous=null;double previousTime=-1,previousY=0;
        var recentMotion=new Queue<(double Time,double Speed)>();
        var samples=new List<MotionSample>();
        for(int i=0;i<frames.Count;i++)
        {
            token.ThrowIfCancellationRequested();var f=frames[i];var s=f.ShaftForAthlete(athleteId);
            // Filtering another owner's observation must not turn a real transfer
            // into an apparently empty gap between two samples of the old owner.
            if(previous?.AthleteId is {} previousOwner && f.GetShafts().Any(bar=>
                bar.TrackId==previous.TrackId && bar.AthleteId is {} owner && owner!=previousOwner))
                previous=null;
            if(s is null || s.Confidence<.5 || !references.TryGetValue(s.TrackId,out double x))continue;
            x=referenceX;
            var lines=s.Segments.Where(l=>Math.Abs(l.X2-l.X1)>2).Select(l=>new {
                Y=l.Y1+(x-l.X1)*(l.Y2-l.Y1)/(l.X2-l.X1), Weight=Math.Abs(l.X2-l.X1)}).OrderBy(l=>l.Y).ToArray();
            if(lines.Length==0)continue;
            double half=lines.Sum(l=>l.Weight)/2,weight=0,y=lines[^1].Y;
            foreach(var l in lines){weight+=l.Weight;if(weight>=half){y=l.Y;break;}}
            bool repaired=false;
            while(recentMotion.Count>0 && f.TimestampSeconds-recentMotion.Peek().Time>.15)recentMotion.Dequeue();
            double elapsed=f.TimestampSeconds-previousTime;
            bool reacquired=previous is not null && elapsed>.15 && elapsed<=.25 &&
                s.TrackId==previous.TrackId && s.AthleteId is not null && s.AthleteId==previous.AthleteId;
            bool same=previous is not null && elapsed>0 && (elapsed<=.15 || reacquired);
            if(same)
            {
                // Compare the SAME visible part across frames. A fragment appearing behind a hand
                // must not shift the measured position just because the set of segments changed.
                var matches=(from a in previous!.Segments from b in s.Segments
                    let left=Math.Max(Math.Min(a.X1,a.X2),Math.Min(b.X1,b.X2))
                    let right=Math.Min(Math.Max(a.X1,a.X2),Math.Max(b.X1,b.X2))
                    where right-left>4 && Math.Abs(a.X2-a.X1)>2 && Math.Abs(b.X2-b.X1)>2
                    where !reacquired || (right-left>=Math.Min(Math.Abs(a.X2-a.X1),Math.Abs(b.X2-b.X1))*.5 &&
                        Math.Abs(Math.Atan((a.Y2-a.Y1)/(a.X2-a.X1))-Math.Atan((b.Y2-b.Y1)/(b.X2-b.X1)))<Math.PI/22.5)
                    let mx=(left+right)/2
                    let dy=b.Y1+(mx-b.X1)*(b.Y2-b.Y1)/(b.X2-b.X1)-a.Y1-(mx-a.X1)*(a.Y2-a.Y1)/(a.X2-a.X1)
                    where Math.Abs(dy)<Math.Max(10,(right-left)*.3)
                    orderby right-left descending select dy).ToArray();
                bool ownerCompatible=s.AthleteId==null || previous.AthleteId==null || s.AthleteId==previous.AthleteId;
                if(matches.Length>0 && ownerCompatible){y=previousY+matches[0];repaired=reacquired;}
                else if(!reacquired && s.TrackId==previous.TrackId && s.MotionReliable && ownerCompatible)y=previousY+s.DeltaY;
                else if(!reacquired && ownerCompatible && fragmentBridges<2 &&
                    TryMovingOverlap(previous,s,f.TimestampSeconds-previousTime,recentMotion.Select(m=>m.Speed).ToArray(),out double measured))
                {
                    y=previousY+measured;
                    repaired=true;
                }
                else if(!reacquired && ownerCompatible && fragmentBridges<2 &&
                    TryFragmentTransition(previous,s,out double displacement))
                {
                    y=previousY+displacement;
                    repaired=true;
                }
                else same=false;
            }
            fragmentBridges=repaired?fragmentBridges+1:0;
            if(!same){continuity++;recentMotion.Clear();}
            if(s.MotionReliable && s.DeltaSeconds>0 && s.DeltaSeconds<=.15 && double.IsFinite(s.DeltaY))
            {
                recentMotion.Enqueue((f.TimestampSeconds,s.DeltaY/s.DeltaSeconds));
                while(recentMotion.Count>3)recentMotion.Dequeue();
            }
            samples.Add(new(i,f.TimestampSeconds,new(x,y),new(x,y),s.Confidence,
                s.MotionReliable && !repaired?AnalysisQuality.Good:AnalysisQuality.Reduced){ContinuityId=continuity});
            previous=s;previousTime=f.TimestampSeconds;previousY=y;
        }
        return samples;
    }

    private static bool TryMovingOverlap(ShaftObservation previous,ShaftObservation current,double elapsed,
        double[] speeds,out double displacement)
    {
        displacement=0;
        if(speeds.Length<2)return false;
        double speed=speeds.Order().ElementAt(speeds.Length/2),expected=speed*elapsed;
        if(Math.Abs(expected)<3 || speeds.Any(v=>v*speed<=0 || Math.Abs(v-speed)>Math.Abs(speed)*.6))return false;
        var candidates=new List<double>();
        foreach(var a in previous.Segments)
        foreach(var b in current.Segments)
        {
            double widthA=Math.Abs(a.X2-a.X1),widthB=Math.Abs(b.X2-b.X1);
            double left=Math.Max(Math.Min(a.X1,a.X2),Math.Min(b.X1,b.X2));
            double right=Math.Min(Math.Max(a.X1,a.X2),Math.Max(b.X1,b.X2));
            double overlap=right-left;
            if(widthA<12 || widthB<12 || overlap<Math.Max(12,Math.Min(widthA,widthB)*.4))continue;
            double slopeA=(a.Y2-a.Y1)/(a.X2-a.X1),slopeB=(b.Y2-b.Y1)/(b.X2-b.X1);
            if(Math.Abs(Math.Atan(slopeA)-Math.Atan(slopeB))>Math.PI/22.5)continue;
            double x=(left+right)/2;
            double measured=b.Y1+(x-b.X1)*slopeB-a.Y1-(x-a.X1)*slopeA;
            double tolerance=Math.Max(3,Math.Min(overlap*.12,Math.Abs(expected)*.25));
            if(double.IsFinite(measured) && measured*expected>0 && Math.Abs(measured-expected)<=tolerance)candidates.Add(measured);
        }
        if(candidates.Count==0 || candidates.Max()-candidates.Min()>Math.Max(4,Math.Abs(expected)*.2))return false;
        // Forecast is only an association gate: retain a measured displacement, never
        // replace missing observations with predicted positions or extrapolated samples.
        displacement=candidates.MinBy(d=>Math.Abs(d-expected));
        return true;
    }

    private static bool TryFragmentTransition(ShaftObservation previous,ShaftObservation current,out double displacement)
    {
        displacement=0;
        // A changed fragment has no shared pixels. Only bridge nearby, aligned fragments
        // of an identified bar; never infer a trajectory through sustained detection loss.
        if(previous.TrackId!=current.TrackId &&
            (previous.AthleteId is null || previous.AthleteId!=current.AthleteId))return false;
        double bestGap=double.PositiveInfinity;
        foreach(var a in previous.Segments)
        foreach(var b in current.Segments)
        {
            double widthA=Math.Abs(a.X2-a.X1),widthB=Math.Abs(b.X2-b.X1);
            if(widthA<12 || widthB<12)continue;
            double left=Math.Max(Math.Min(a.X1,a.X2),Math.Min(b.X1,b.X2));
            double right=Math.Min(Math.Max(a.X1,a.X2),Math.Max(b.X1,b.X2));
            double gap=left-right;
            if(gap<0 || gap>Math.Max(30,Math.Max(widthA,widthB)*1.5) || gap>=bestGap)continue;
            double slopeA=(a.Y2-a.Y1)/(a.X2-a.X1),slopeB=(b.Y2-b.Y1)/(b.X2-b.X1);
            if(Math.Abs(Math.Atan(slopeA)-Math.Atan(slopeB))>Math.PI/45)continue;
            double x=(left+right)/2;
            double dy=b.Y1+(x-b.X1)*slopeB-a.Y1-(x-a.X1)*slopeA;
            if(!double.IsFinite(dy) || Math.Abs(dy)>Math.Max(8,Math.Min(widthA,widthB)*.3))continue;
            bestGap=gap;
            displacement=dy;
        }
        return double.IsFinite(bestGap);
    }
}

public static class MotionGapRepair
{
    public static IReadOnlyList<MotionSample> FillShortGaps(IReadOnlyList<MotionSample> input,int height)
    {
        var result=input.ToArray();
        for(int i=1;i<result.Length-1;i++)
        {
            if(result[i].Confidence>=.4)continue;
            int start=i;while(i<result.Length && result[i].Confidence<.4)i++;
            if(i==result.Length)break;
            var a=result[start-1];var b=result[i];double span=b.TimestampSeconds-a.TimestampSeconds;
            if(a.Confidence<.4 || i-start>3 || span<=0 || span>.15 || a.ContinuityId!=b.ContinuityId ||
                !double.IsFinite(a.Position.Y) || !double.IsFinite(b.Position.Y) || Math.Abs(b.Position.Y-a.Position.Y)>height*.04)continue;
            for(int k=start;k<i;k++)
            {
                double f=(result[k].TimestampSeconds-a.TimestampSeconds)/span;
                result[k]=result[k] with {Position=new(a.Position.X+(b.Position.X-a.Position.X)*f,a.Position.Y+(b.Position.Y-a.Position.Y)*f),
                    Confidence=Math.Min(a.Confidence,b.Confidence),Quality=AnalysisQuality.Reduced,IsInterpolated=true};
            }
        }
        return result;
    }
}
public sealed record PixelScaleCalibration(double MetersPerPixel)
{
    public double ToMeters(double pixels)=>double.IsFinite(MetersPerPixel) && MetersPerPixel>0?pixels*MetersPerPixel:throw new InvalidOperationException("Invalid scale calibration.");
}

internal sealed class SampleRange<T>(IReadOnlyList<T> source,int start,int count) : IReadOnlyList<T>
{
    public int Count=>count;
    public T this[int index]=>index>=0 && index<count?source[start+index]:throw new ArgumentOutOfRangeException(nameof(index));
    public IEnumerator<T> GetEnumerator(){for(int i=0;i<count;i++)yield return source[start+i];}
    System.Collections.IEnumerator System.Collections.IEnumerable.GetEnumerator()=>GetEnumerator();
}

public static class PlaybackSampleLookup
{
    /// <summary>Exact timestamp interpolation inside a continuous segment; never extrapolate through missing data.</summary>
    public static MovementPoint? At(IReadOnlyList<MovementPoint> points,double time)
    {
        if(!double.IsFinite(time))return null;
        int low=0,high=points.Count-1;
        while(low<=high){int mid=(low+high)/2;if(points[mid].Time<time)low=mid+1;else high=mid-1;}
        if(low<points.Count && Math.Abs(points[low].Time-time)<1e-8)return points[low];
        if(high<0 || low>=points.Count)return null;
        var a=points[high];var b=points[low];
        if(a.Segment!=b.Segment || b.Time-a.Time>.25)return null;
        double f=(time-a.Time)/(b.Time-a.Time);
        return a with {Time=time,Y=a.Y+(b.Y-a.Y)*f,Velocity=a.Velocity+(b.Velocity-a.Velocity)*f,
            Confidence=Math.Min(a.Confidence,b.Confidence),Quality=(AnalysisQuality)Math.Max((int)a.Quality,(int)b.Quality)};
    }
}
