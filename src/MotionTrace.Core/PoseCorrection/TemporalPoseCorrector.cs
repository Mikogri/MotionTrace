using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
namespace MotionTrace.Core.PoseCorrection;

public sealed class TemporalPoseCorrector(PoseCorrectionOptions options, IPoseSmoother smoother)
{
    public const string Version="temporal-1";
    public AnalysisResult Correct(AnalysisResult raw,CancellationToken token=default)
    {
        if(options.MaximumInterpolationFrames<0 || !double.IsFinite(options.MaximumInterpolationSeconds) || options.MaximumInterpolationSeconds<0 || !double.IsFinite(options.MinimumConfidence) || options.MinimumConfidence is <=0 or >1 || !double.IsFinite(options.OutlierDistanceInBodyLengths) || options.OutlierDistanceInBodyLengths<=0)
            throw new ArgumentException("Invalid pose correction configuration.");
        var frames=raw.Frames.Select(f=>f.Athletes.Select(p=>p.TrackingState==TrackingState.Lost?p with {Quality=AnalysisQuality.Poor}:p).ToArray()).ToArray();
        foreach(var athlete in raw.Athletes)
        {
            var segment=new List<(int Frame,int Pose)>();
            for(int f=0;f<frames.Length;f++)
            {
                token.ThrowIfCancellationRequested();
                int p=Array.FindIndex(frames[f],p=>p.AthleteId==athlete.Id && p.TrackingState==TrackingState.Tracked && p.Keypoints.Count>0);
                if(p<0 || (segment.Count>0 && raw.Frames[f].TimestampSeconds-raw.Frames[segment[^1].Frame].TimestampSeconds>.15))
                { Process(segment);segment.Clear(); }
                if(p>=0)segment.Add((f,p));
            }
            Process(segment);
            void Process(List<(int Frame,int Pose)> segment)
            {
                if(segment.Count==0)return;
                token.ThrowIfCancellationRequested();
                var poses=segment.Select(s=>frames[s.Frame][s.Pose]).ToArray();
                var times=segment.Select(s=>raw.Frames[s.Frame].TimestampSeconds).ToArray();
                var scales=poses.Select(PoseGeometry.Scale).ToArray();
                var points=poses.Select(p=>Enumerable.Range(0,17).Select(j=>p.Keypoints.FirstOrDefault(k=>(int)k.Joint==j) ?? new((Joint)j,new(0,0),0)).ToArray()).ToArray();
                SideSwapCorrector.Correct(points,times,scales);
                JointOutlierDetector.Reject(points,times,scales,options);
                LimbConsistencyValidator.Reject(points,times,scales);
                ShortGapInterpolator.Fill(points,times,options);
                for(int j=0;j<17;j++)
                {
                    token.ThrowIfCancellationRequested();
                    var series=points.Select(p=>p[j]).ToArray();
                    for(int i=0;i<points.Length;i++)
                    {
                        var position=smoother.Smooth(series,times,i);
                        points[i][j]=points[i][j] with {Position=position,IsCorrected=points[i][j].IsCorrected || position!=points[i][j].RawPosition};
                    }
                }
                for(int i=0;i<segment.Count;i++)
                {
                    var pose=poses[i];double risk=pose.OcclusionRisk switch{OcclusionRisk.High=>.45,OcclusionRisk.Medium=>.8,_=>1};
                    var clean=points[i].Select(k=>k with {Confidence=k.Confidence*pose.TrackingConfidence*risk,TrackingConfidence=pose.TrackingConfidence*risk}).ToArray();
                    double missing=clean.Count(k=>k.Confidence<options.MinimumConfidence)/(double)clean.Length;
                    var quality=pose.OcclusionRisk==OcclusionRisk.High || missing>.5?AnalysisQuality.Poor:
                        missing>.15 || clean.Any(k=>k.IsOutlier || k.IsInterpolated) || pose.OcclusionRisk==OcclusionRisk.Medium?AnalysisQuality.Reduced:AnalysisQuality.Good;
                    frames[segment[i].Frame][segment[i].Pose]=pose with {Keypoints=clean,Quality=quality};
                }
            }
        }
        return raw with { Frames=raw.Frames.Select((f,i)=>f with {Athletes=frames[i]}).ToArray(),
            Versions=raw.Versions with {CorrectionVersion=$"{Version}:{options}"} };
    }
}

public sealed class CorrectingPoseEngine(IPoseAnalysisEngine rawEngine,TemporalPoseCorrector corrector) : IPoseAnalysisEngine
{
    public async Task<AnalysisResult> AnalyzeAsync(string path,IProgress<AnalysisProgress> progress,CancellationToken token)
    {
        var raw=await rawEngine.AnalyzeAsync(path,progress,token);
        progress.Report(new("Correcting pose trajectories"));
        return await Task.Run(()=>corrector.Correct(raw,token),token);
    }
}
