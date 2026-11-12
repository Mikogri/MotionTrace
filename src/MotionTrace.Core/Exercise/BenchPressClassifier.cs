using MotionTrace.Core.Athletes;

namespace MotionTrace.Core.Exercise;

/// <summary>Conservative, experimental 2D rules. Score is evidence strength, not a probability.</summary>
public sealed class BenchPressClassifier : IExerciseClassifier
{
    public const string Version = "bench-rules-0.1";
    public const double WindowSeconds = 6;
    public ExerciseClassification Classify(IReadOnlyList<PoseFrame> frames, int athleteId)
    {
        var unknown = new ExerciseClassification(ExerciseType.Unknown, 0,
            "Experimental: needs a visible reclining torso and a complete arm movement. Squat/deadlift are not supported.");
        if (frames.Count == 0) return unknown;
        double end = frames[^1].TimestampSeconds;
        var samples = new List<(double Time, double Angle, double Wrist, bool Reclining)>();
        // Use a single visible body side throughout each candidate window.
        ExerciseClassification best = unknown;
        foreach (bool left in new[] { true, false })
        {
            samples.Clear();
            double last = double.NegativeInfinity;
            foreach (var frame in frames)
            {
                if (frame.TimestampSeconds < end - WindowSeconds || frame.TimestampSeconds - last < .09) continue;
                var pose = frame.Athletes.FirstOrDefault(p => p.AthleteId == athleteId);
                if (pose is null || pose.Confidence < .5 || pose.TrackingState==TrackingState.Lost || pose.Quality==AnalysisQuality.Poor) continue;
                Keypoint? Get(Joint joint) => pose.Keypoints.FirstOrDefault(k => k.Joint == joint && k.Confidence >= .3 && double.IsFinite(k.Position.X) && double.IsFinite(k.Position.Y));
                var s = Get(left ? Joint.LeftShoulder : Joint.RightShoulder);
                var e = Get(left ? Joint.LeftElbow : Joint.RightElbow);
                var w = Get(left ? Joint.LeftWrist : Joint.RightWrist);
                var h = Get(left ? Joint.LeftHip : Joint.RightHip);
                if (s is null || e is null || w is null || h is null) continue;
                double dx = h.Position.X - s.Position.X, dy = h.Position.Y - s.Position.Y;
                double torso = Math.Sqrt(dx * dx + dy * dy);
                if (torso < 10) continue;
                double ax = s.Position.X - e.Position.X, ay = s.Position.Y - e.Position.Y;
                double bx = w.Position.X - e.Position.X, by = w.Position.Y - e.Position.Y;
                double norm = Math.Sqrt((ax * ax + ay * ay) * (bx * bx + by * by));
                if (norm < 1) continue;
                double angle = Math.Acos(Math.Clamp((ax * bx + ay * by) / norm, -1, 1)) * 180 / Math.PI;
                samples.Add((frame.TimestampSeconds, angle, (s.Position.Y - w.Position.Y) / torso, Math.Abs(dy) / torso < .70));
                last = frame.TimestampSeconds;
            }
            if (samples.Count < 15 || samples[^1].Time - samples[0].Time < 2 || end - samples[^1].Time > .3) continue;
            if (samples.Zip(samples.Skip(1), (a,b) => b.Time-a.Time).Any(gap => gap > .5)) continue;
            var recent = samples.Where(s => s.Time >= end - .7).ToArray();
            if (recent.Length < 3 || recent.Count(s => s.Reclining && s.Wrist > .10) < recent.Length * .7) continue;
            double reclining = samples.Count(s => s.Reclining) / (double)samples.Count;
            double raised = samples.Count(s => s.Wrist > .10) / (double)samples.Count;
            var angles = samples.Select(s => s.Angle).Order().ToArray();
            var wrists = samples.Select(s => s.Wrist).Order().ToArray();
            double excursion = angles[(int)(angles.Length * .9)] - angles[(int)(angles.Length * .1)];
            double travel = wrists[(int)(wrists.Length * .9)] - wrists[(int)(wrists.Length * .1)];
            // Require a reversal, not just reaching up once during setup.
            var smooth = Enumerable.Range(1, samples.Count - 2).Select(i =>
                (samples[i-1].Angle + samples[i].Angle + samples[i+1].Angle) / 3).ToArray();
            bool cycle = false;
            for (int i = 2; i < smooth.Length-2; i++)
                if ((smooth.Take(i).Max()-smooth[i] > 18 && smooth.Skip(i+1).Max()-smooth[i] > 18) ||
                    (smooth[i]-smooth.Take(i).Min() > 18 && smooth[i]-smooth.Skip(i+1).Min() > 18)) { cycle = true; break; }
            if (reclining < .75 || raised < .70 || excursion < 28 || travel < .12 || !cycle) continue;
            double score = Math.Clamp(.5 * reclining + .25 * raised + .25 * Math.Min(1, excursion / 70), 0, 1);
            if (score > best.Confidence) best = new(ExerciseType.BenchPress, score,
                "Experimental rule score, not probability. Setup or other lying exercises may resemble bench press; no squat/deadlift validation.");
        }
        return best;
    }
}
