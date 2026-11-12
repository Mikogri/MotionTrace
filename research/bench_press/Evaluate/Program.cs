using MotionTrace.Core.Exercise;
using MotionTrace.Infrastructure.AI;
var classifier = new BenchPressClassifier();
foreach (var path in args.Where(a=>!a.StartsWith("--"))) {
 using var stream = File.OpenRead(path);
 var result = await AnalysisJson.ReadAsync(stream);
 if(args.Contains("--corrected")) {
  result=new MotionTrace.Core.PoseCorrection.TemporalPoseCorrector(new(),new MotionTrace.Core.PoseCorrection.LightPoseSmoother()).Correct(result);
  var keys=result.Frames.SelectMany(f=>f.Athletes).SelectMany(p=>p.Keypoints).ToArray();
  Console.WriteLine($"Correction: {keys.Count(k=>k.IsOutlier)} outliers, {keys.Count(k=>k.IsInterpolated)} interpolated / {keys.Length} points. {result.Frames.SelectMany(f=>f.Athletes).Count(p=>p.Quality==MotionTrace.Core.Athletes.AnalysisQuality.Poor)} poor poses.");
 }
 Console.WriteLine($"{result.Video.FileName}: {result.Video.Width}x{result.Video.Height}");
 foreach(var athlete in result.Athletes) {
 if(args.Contains("--movement")) {
  foreach(var wrist in new[]{MotionTrace.Core.Athletes.Joint.LeftWrist,MotionTrace.Core.Athletes.Joint.RightWrist}) {
   var motion=MotionTrace.Core.Motion.MovementAnalyzer.Analyze(result.Frames,athlete.Id,wrist,ExerciseType.BenchPress,result.Video.Height);
   Console.WriteLine($"Track {athlete.Id} {wrist}: {motion.Reps.Count} candidate reps");
   foreach(var rep in motion.Reps) Console.WriteLine($"  {rep.Label}, down {rep.Lowering?.Duration:0.00}s, pause {rep.PauseSeconds:0.00}s, up {rep.Lifting.Duration:0.00}s");
  }
  continue;
 }
 var positive = new List<double>();
 for(double t=0;t<result.Video.DurationSeconds;t+=.5) {
 var window=result.Frames.Where(f=>f.TimestampSeconds>=t-6 && f.TimestampSeconds<=t).ToList();
 window.Add(new(t, []));
 var c=classifier.Classify(window,athlete.Id);
 if(c.ExerciseType==ExerciseType.BenchPress) positive.Add(t);
 }
 Console.WriteLine($"Track {athlete.Id}: {string.Join(",",positive.Select(t=>t.ToString("0.0",System.Globalization.CultureInfo.InvariantCulture)))}");
 }
}
