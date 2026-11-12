using System.Text.Json;
using MotionTrace.Infrastructure.AI;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.Motion;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.PoseCorrection;

using var stream=File.OpenRead(args[0]);
var raw=await AnalysisJson.ReadAsync(stream);
var result=new TemporalPoseCorrector(new(),new LightPoseSmoother()).Correct(raw);
var rows=new List<object>();
var exercise=args.Length>1?Enum.Parse<ExerciseType>(args[1],true):ExerciseType.BenchPress;
foreach(var athlete in result.Athletes)
foreach(var wrist in new[]{Joint.LeftWrist,Joint.RightWrist})
{
    var candidates=MovementAnalyzer.Analyze(result.Frames,athlete.Id,wrist,exercise,result.Video.Height);
    var gated=ShaftRepGate.Apply(candidates,result.Frames,athlete.Id,result.Video.Height);
    var rawCandidates=MovementAnalyzer.Analyze(raw.Frames,athlete.Id,wrist,exercise,result.Video.Height);
    rows.Add(new{athlete=athlete.Id,wrist=wrist.ToString(),candidates=candidates.Reps.Count,confirmed=gated.Reps.Count,
        rawCandidates=rawCandidates.Reps.Count,validSamples=new WristTrajectoryProvider().Extract(result.Frames,athlete.Id,wrist).Count(s=>s.Confidence>=.4),
        segments=candidates.Points.Select(p=>p.Segment).Distinct().Count(),
        analyzedSamples=candidates.Points.Count,
        candidateTimes=candidates.Reps.Select(r=>new{r.Start,r.End}),reps=gated.Reps.Select(r=>new{r.Start,r.End,lowering=r.Lowering?.Duration,lifting=r.Lifting.Duration,peak=r.Lifting.PeakSpeed})});
}
var shaftAnalyses=result.Athletes.Select(a=> {
    var samples=MeasurementSources.Barbell(result).Extract(result.Frames,a.Id,Joint.LeftWrist);
    var analysis=MovementAnalyzer.AnalyzeTrajectory(samples,exercise,result.Video.Height);
    return new {athlete=a.Id,participant=a.IsExerciseParticipant,samples=samples.Count,analysis};
}).ToArray();
var shaftByAthlete=shaftAnalyses.Select(a=>new {
    a.athlete,a.participant,a.samples,source=MeasurementSources.BarbellLabel(result,a.athlete),
    segments=a.analysis.Points.Select(p=>p.Segment).Distinct().Count(),
    reps=a.analysis.Reps.Select(r=>new{r.Start,r.End,loweringStart=r.Lowering?.Start,loweringEnd=r.Lowering?.End,
        liftingStart=r.Lifting.Start,liftingEnd=r.Lifting.End,lowering=r.Lowering?.Duration,lifting=r.Lifting.Duration,peak=r.Lifting.PeakSpeed})
}).ToArray();
File.WriteAllText(args[0]+".shaft-points.json",JsonSerializer.Serialize(shaftAnalyses.Select(a=>new{a.athlete,points=a.analysis.Points})));
Console.WriteLine(JsonSerializer.Serialize(new{frames=result.Frames.Count,
    detected=result.Frames.Count(f=>f.GetShafts().Any()),
    reliable=result.Frames.Count(f=>f.GetShafts().Any(s=>s.MotionReliable)),
    assigned=result.Frames.Count(f=>f.GetShafts().Any(s=>s.AthleteId!=null)),
    shaftObservations=result.Frames.Sum(f=>f.GetShafts().Count()),
    reliableObservations=result.Frames.Sum(f=>f.GetShafts().Count(s=>s.MotionReliable)),
    assignedObservations=result.Frames.Sum(f=>f.GetShafts().Count(s=>s.AthleteId!=null)),
    shaftSegments=shaftByAthlete.Sum(a=>a.segments),shaftSamples=shaftByAthlete.Sum(a=>a.samples),shaftByAthlete,
    shaftReps=shaftByAthlete.SelectMany(a=>a.reps.Select(r=>new {a.athlete,r.Start,r.End,r.loweringStart,r.loweringEnd,
        r.liftingStart,r.liftingEnd,r.lowering,r.lifting,r.peak})),rows},new JsonSerializerOptions{WriteIndented=true}));
