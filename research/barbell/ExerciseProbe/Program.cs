using System.Text.Json;
using MotionTrace.Infrastructure.AI;
using MotionTrace.Core.Exercise;
using MotionTrace.Core.Motion;
using MotionTrace.Core.Athletes;
using MotionTrace.Core.PoseCorrection;

var rows = new List<object>();
foreach (var path in args)
{
    using var stream = File.OpenRead(path);
    var raw = await AnalysisJson.ReadAsync(stream);
    var analysis = new TemporalPoseCorrector(new(), new LightPoseSmoother()).Correct(raw);
    foreach (var athlete in analysis.Athletes.Where(a => a.IsExerciseParticipant))
    {
        var resolved = ExerciseResolver.Resolve(analysis, athlete.Id);
        var fallback = ExerciseResolver.Resolve(analysis with { ExercisePredictions = [] }, athlete.Id);
        var legacy = ExerciseType.Unknown;
        if (analysis.AnalysisSchemaVersion < 4)
        {
            var classifier = new BenchPressClassifier();
            var timeline = new List<ExerciseClassification>();
            for (int index = 0; index <= Math.Ceiling(analysis.Video.DurationSeconds * 2); index++)
            {
                double time = index / 2.0;
                var window = analysis.Frames.Where(f => f.TimestampSeconds >= time - BenchPressClassifier.WindowSeconds && f.TimestampSeconds <= time).ToList();
                if (window.Count == 0 || time - window[^1].TimestampSeconds > .01) window.Add(new(time, []));
                timeline.Add(classifier.Classify(window, athlete.Id));
            }
            legacy = timeline.Where(c => c.ExerciseType is ExerciseType.BenchPress or ExerciseType.Squat or ExerciseType.Deadlift)
                .GroupBy(c => c.ExerciseType).OrderByDescending(g => g.Count()).Select(g => g.Key).FirstOrDefault();
        }
        var selected = resolved.ExerciseType != ExerciseType.Unknown ? resolved.ExerciseType : legacy;
        var bar = MeasurementSources.Barbell(analysis).Extract(analysis.Frames, athlete.Id, Joint.LeftWrist);
        var reps = new[] { ExerciseType.BenchPress, ExerciseType.Deadlift }.Select(e => new { exercise = e.ToString(),
            times = MovementAnalyzer.AnalyzeTrajectory(bar, e, analysis.Video.Height).Reps.Select(r => new { r.Start, r.End }) });
        rows.Add(new { file = Path.GetFileName(path), athlete = athlete.Id, exercise = resolved.ExerciseType.ToString(),
            resolved.Confidence, resolved.Limitation, fallback = fallback.ExerciseType.ToString(), legacy = legacy.ToString(), selected = selected.ToString(), corrected = true, reps });
    }
}
Console.WriteLine(JsonSerializer.Serialize(rows, new JsonSerializerOptions { WriteIndented = true }));
