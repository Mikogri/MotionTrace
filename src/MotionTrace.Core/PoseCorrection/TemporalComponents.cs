using MotionTrace.Core.Athletes;
namespace MotionTrace.Core.PoseCorrection;

public sealed record PoseCorrectionOptions(int MaximumInterpolationFrames=3, double MaximumInterpolationSeconds=.15,
    double MinimumConfidence=.4, double OutlierDistanceInBodyLengths=.08);

internal static class PoseGeometry
{
    public static double Distance(Point2 a,Point2 b)=>Math.Sqrt(Math.Pow(a.X-b.X,2)+Math.Pow(a.Y-b.Y,2));
    public static Point2 Lerp(Point2 a,Point2 b,double t)=>new(a.X+(b.X-a.X)*t,a.Y+(b.Y-a.Y)*t);
    public static double Scale(AthletePose p)=>Math.Max(1,Math.Sqrt(p.BoundingBox.Width*p.BoundingBox.Width+p.BoundingBox.Height*p.BoundingBox.Height));
}

internal static class SideSwapCorrector
{
    private static readonly (Joint,Joint)[] Pairs=[(Joint.LeftWrist,Joint.RightWrist),(Joint.LeftElbow,Joint.RightElbow),(Joint.LeftKnee,Joint.RightKnee),(Joint.LeftAnkle,Joint.RightAnkle)];
    public static void Correct(Keypoint[][] points,double[] times,double[] scales)
    {
        foreach(var (left,right) in Pairs)
        for(int i=1;i<points.Length-1;i++)
        {
            int l=(int)left,r=(int)right;
            for(int length=1;length<=3 && i+length<points.Length;length++)
            {
                int end=i+length;
                if(times[end]-times[i-1]>.25)break;
                var pl=points[i-1][l];var pr=points[i-1][r];var nl=points[end][l];var nr=points[end][r];
                if(new[]{pl,pr,nl,nr}.Any(p=>p.Confidence<.4))continue;
                bool swap=true;
                for(int k=i;k<end;k++)
                {
                    var a=points[k][l];var b=points[k][r];
                    if(a.Confidence<.4 || b.Confidence<.4){swap=false;break;}
                    double Direct(Keypoint x,Keypoint y)=>PoseGeometry.Distance(a.Position,x.Position)+PoseGeometry.Distance(b.Position,y.Position);
                    double Swapped(Keypoint x,Keypoint y)=>PoseGeometry.Distance(b.Position,x.Position)+PoseGeometry.Distance(a.Position,y.Position);
                    if(!(Swapped(pl,pr)+scales[k]*.04<Direct(pl,pr)*.5 && Swapped(nl,nr)+scales[k]*.04<Direct(nl,nr)*.5)){swap=false;break;}
                }
                if(!swap)continue;
                for(int k=i;k<end;k++)
                {
                    var a=points[k][l];var b=points[k][r];
                    points[k][l]=a with {Position=b.Position,Confidence=Math.Min(a.Confidence,b.Confidence)*.8,IsCorrected=true};
                    points[k][r]=b with {Position=a.Position,Confidence=Math.Min(a.Confidence,b.Confidence)*.8,IsCorrected=true};
                }
                i=end-1;break;
            }
        }
    }
}

internal static class JointOutlierDetector
{
    public static void Reject(Keypoint[][] points,double[] times,double[] scales,PoseCorrectionOptions options)
    {
        var rejects=new List<(int,int)>();
        for(int i=1;i<points.Length-1;i++)for(int j=0;j<17;j++)
        {
            var a=points[i-1][j];var b=points[i][j];var c=points[i+1][j];
            double before=times[i]-times[i-1],after=times[i+1]-times[i];
            if(before>.15 || after>.15 || a.Confidence<options.MinimumConfidence || c.Confidence<options.MinimumConfidence)continue;
            var expected=PoseGeometry.Lerp(a.Position,c.Position,before/(before+after));
            double residual=PoseGeometry.Distance(b.Position,expected)/scales[i];
            double speed=PoseGeometry.Distance(b.Position,a.Position)/before/scales[i];
            double acceleration=residual/(before*after);
            if(residual>options.OutlierDistanceInBodyLengths && speed>1.5 && acceleration>15 &&
                PoseGeometry.Distance(a.Position,c.Position)/scales[i]<.15) rejects.Add((i,j));
        }
        foreach(var (i,j) in rejects)points[i][j]=points[i][j] with {Confidence=0,IsOutlier=true};
    }
}

internal static class LimbConsistencyValidator
{
    private static readonly (Joint,Joint)[] Limbs=[(Joint.LeftShoulder,Joint.LeftElbow),(Joint.LeftElbow,Joint.LeftWrist),(Joint.RightShoulder,Joint.RightElbow),(Joint.RightElbow,Joint.RightWrist),(Joint.LeftHip,Joint.LeftKnee),(Joint.LeftKnee,Joint.LeftAnkle),(Joint.RightHip,Joint.RightKnee),(Joint.RightKnee,Joint.RightAnkle)];
    public static void Reject(Keypoint[][] points,double[] times,double[] scales)
    {
        var invalid=new HashSet<(int,int)>();
        foreach(var (a,b) in Limbs)
        for(int i=0;i<points.Length;i++)
        {
            int l=(int)a,r=(int)b;
            if(Math.Min(points[i][l].Confidence,points[i][r].Confidence)<.4)continue;
            var lengths=new List<double>();
            for(int k=i-1;k>=0 && times[i]-times[k]<.5;k--)
                if(Math.Min(points[k][l].Confidence,points[k][r].Confidence)>=.5)lengths.Add(PoseGeometry.Distance(points[k][l].Position,points[k][r].Position)/scales[k]);
            for(int k=i+1;k<points.Length && times[k]-times[i]<.5;k++)
                if(Math.Min(points[k][l].Confidence,points[k][r].Confidence)>=.5)lengths.Add(PoseGeometry.Distance(points[k][l].Position,points[k][r].Position)/scales[k]);
            if(lengths.Count<5)continue;
            lengths.Sort();double baseline=lengths[lengths.Count/2];
            double actual=PoseGeometry.Distance(points[i][l].Position,points[i][r].Position)/scales[i];
            if(baseline>.02 && (actual>baseline*2.2 || actual<baseline*.3))invalid.Add((i,r));
        }
        foreach(var (i,j) in invalid)points[i][j]=points[i][j] with {Confidence=0,IsOutlier=true};
    }
}

internal static class ShortGapInterpolator
{
    public static void Fill(Keypoint[][] points,double[] times,PoseCorrectionOptions options)
    {
        for(int j=0;j<17;j++)
        for(int i=0;i<points.Length;i++)
        {
            if(points[i][j].Confidence>=options.MinimumConfidence)continue;
            int start=i;
            while(i<points.Length && points[i][j].Confidence<options.MinimumConfidence)i++;
            int end=i;
            if(start==0 || end==points.Length || end-start>options.MaximumInterpolationFrames || times[end]-times[start-1]>options.MaximumInterpolationSeconds)continue;
            for(int k=start;k<end;k++)points[k][j]=points[k][j] with {
                Position=PoseGeometry.Lerp(points[start-1][j].Position,points[end][j].Position,(times[k]-times[start-1])/(times[end]-times[start-1])),
                Confidence=Math.Min(.5,Math.Min(points[start-1][j].Confidence,points[end][j].Confidence)*.7),IsCorrected=true,IsInterpolated=true};
        }
    }
}

public interface IPoseSmoother
{
    Point2 Smooth(IReadOnlyList<Keypoint> points,IReadOnlyList<double> times,int index);
}
public sealed class LightPoseSmoother : IPoseSmoother
{
    public Point2 Smooth(IReadOnlyList<Keypoint> points,IReadOnlyList<double> times,int i)
    {
        if(i==0 || i==points.Count-1 || points[i].Confidence<.4 || points[i-1].Confidence<.4 || points[i+1].Confidence<.4 || times[i+1]-times[i-1]>.12)return points[i].Position;
        var expected=PoseGeometry.Lerp(points[i-1].Position,points[i+1].Position,(times[i]-times[i-1])/(times[i+1]-times[i-1]));
        return PoseGeometry.Lerp(points[i].Position,expected,.2);
    }
}
