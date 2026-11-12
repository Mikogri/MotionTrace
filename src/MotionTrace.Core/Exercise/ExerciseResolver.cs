using MotionTrace.Core.Analysis;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.Motion;

namespace MotionTrace.Core.Exercise;

/// <summary>Conservative recovery for an unknown video classification, using an owned moving bar and visible anatomy.</summary>
public static class ExerciseResolver
{
    public const string Version = "owned-bar-anatomy-1";

    public static ExerciseClassification Resolve(AnalysisResult analysis, int athleteId)
    {
        ExerciseClassification Unknown(string reason) => new(ExerciseType.Unknown, 0, $"{Version}: {reason}");
        if (!analysis.Athletes.Any(a => a.Id == athleteId && a.IsExerciseParticipant))
            return Unknown("No confirmed exercise participant.");
        var prediction = analysis.ExercisePredictions.FirstOrDefault(p => p.AthleteId == athleteId);
        if (prediction is { Exercise: not ExerciseType.Unknown } && Enum.IsDefined(prediction.Exercise))
            return new(prediction.Exercise, prediction.Score, $"{prediction.Method}: model decision; score is not measurement accuracy.");

        // The legacy shaft provider also accepts unassigned observations. They must not establish an exercise identity.
        var samples = MeasurementSources.Barbell(analysis).Extract(analysis.Frames, athleteId, Joint.LeftWrist)
            .Where(s => analysis.AnalysisSchemaVersion >= 4 || analysis.Frames[s.FrameIndex].GetShafts().Any(b => b.AthleteId == athleteId))
            .ToArray();
        if (samples.Length < 15 || analysis.Video.Height <= 0) return Unknown("Insufficient owned bar motion. Select the exercise manually.");

        var candidates = new List<(ExerciseType Exercise, double Support)>();
        foreach (var exercise in new[] { ExerciseType.BenchPress, ExerciseType.Squat, ExerciseType.Deadlift })
        {
            var movement = MovementAnalyzer.AnalyzeTrajectory(samples, exercise, analysis.Video.Height);
            if (exercise == ExerciseType.BenchPress && movement.Reps.Count > 0)
            {
                // Keep the established bench rule when its visible arm cycle overlaps a real owned-bar rep.
                var bench = new BenchPressClassifier();
                foreach (var rep in movement.Reps)
                {
                    var window = analysis.Frames.Where(f => f.TimestampSeconds >= rep.Start - 1 && f.TimestampSeconds <= rep.End + .2).ToArray();
                    var classification = bench.Classify(window, athleteId);
                    if (classification.ExerciseType == ExerciseType.BenchPress)
                        candidates.Add((ExerciseType.BenchPress, classification.Confidence));
                }
            }
            foreach (var rep in movement.Reps)
            foreach (bool left in new[] { true, false })
            {
                var rows = new List<(double Bar, double Wrist, double Torso, bool Supports)>();
                int expected = 0;
                double evidenceStart = exercise == ExerciseType.Deadlift ? rep.Lifting.Start : rep.Start;
                double evidenceEnd = exercise == ExerciseType.Deadlift ? rep.Lifting.End : rep.End;
                foreach (var sample in samples.Where(s => s.TimestampSeconds >= evidenceStart && s.TimestampSeconds <= evidenceEnd))
                {
                    expected++;
                    var pose = analysis.Frames[sample.FrameIndex].Athletes.FirstOrDefault(p => p.AthleteId == athleteId && p.TrackingState == TrackingState.Tracked);
                    if (pose is null) continue;
                    Keypoint? Get(Joint joint) => pose.Keypoints.FirstOrDefault(k => k.Joint == joint && k.Confidence >= .3 && !k.IsOutlier && !k.IsInterpolated && double.IsFinite(k.Position.X) && double.IsFinite(k.Position.Y));
                    var shoulder = Get(left ? Joint.LeftShoulder : Joint.RightShoulder);
                    var hip = Get(left ? Joint.LeftHip : Joint.RightHip);
                    var wrist = Get(left ? Joint.LeftWrist : Joint.RightWrist);
                    if (shoulder is null || hip is null || wrist is null) continue;
                    double dx = hip.Position.X - shoulder.Position.X, dy = hip.Position.Y - shoulder.Position.Y;
                    double torso = Math.Sqrt(dx * dx + dy * dy);
                    if (torso < 10 || (!sample.IsProxy && Math.Abs(wrist.Position.Y - sample.Position.Y) > torso * .65)) continue;
                    // SAM's mask point can be below the actual shaft (plates/body in the mask).
                    // Its correlated movement confirms activity; visible wrists establish anatomical height.
                    double anatomicalY = sample.IsProxy ? wrist.Position.Y : sample.Position.Y;
                    double upright = dy / torso, bar = (anatomicalY - shoulder.Position.Y) / torso;
                    bool supports = exercise switch
                    {
                        ExerciseType.BenchPress => Math.Abs(upright) < .7 && bar < -.1,
                        ExerciseType.Squat => upright > .5 && bar is > -.4 and < .5,
                        ExerciseType.Deadlift => upright > .5 && bar > .65 && anatomicalY > hip.Position.Y - torso * .25,
                        _ => false
                    };
                    rows.Add((sample.Position.Y, wrist.Position.Y, torso, supports));
                }
                if (rows.Count < 15 || rows.Count < expected * .6) continue;
                double scale = rows.Select(r => r.Torso).Order().ElementAt(rows.Count / 2);
                if (rows.Max(r => r.Bar) - rows.Min(r => r.Bar) < scale * .15 ||
                    rows.Max(r => r.Wrist) - rows.Min(r => r.Wrist) < scale * .15) continue;
                double barMean = rows.Average(r => r.Bar), wristMean = rows.Average(r => r.Wrist);
                double covariance = rows.Sum(r => (r.Bar - barMean) * (r.Wrist - wristMean));
                double norm = Math.Sqrt(rows.Sum(r => Math.Pow(r.Bar - barMean, 2)) * rows.Sum(r => Math.Pow(r.Wrist - wristMean, 2)));
                if (norm <= 0 || covariance / norm < .6) continue;
                double support = rows.Count(r => r.Supports) / (double)rows.Count;
                if (support >= .75) candidates.Add((exercise, support));
            }
        }
        var alternatives = candidates.Select(c => c.Exercise).Distinct().ToArray();
        if (alternatives.Length != 1) return Unknown("No unambiguous complete bar movement with supporting anatomy. Select the exercise manually.");
        return new(alternatives[0], candidates.Max(c => c.Support),
            $"{Version}: experimental fallback from owned bar movement and anatomy; evidence score, not probability. Camera angle and occlusion can require manual selection.");
    }
}
