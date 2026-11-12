namespace MotionTrace.Core.Analysis;

public static class AnalysisSelection
{
    public static IReadOnlySet<int> ParticipantIds(AnalysisResult result) => result.Athletes
        .Where(athlete => athlete.IsExerciseParticipant).Select(athlete => athlete.Id).ToHashSet();

    public static AnalysisResult Filter(AnalysisResult result, IReadOnlySet<int> ids)
    {
        // Selection and export share the same eligibility rule: background tracks stay diagnostic only.
        ids = ParticipantIds(result).Where(ids.Contains).ToHashSet();
        return result with
        {
            Athletes = result.Athletes.Where(a => ids.Contains(a.Id)).ToArray(),
            ExercisePredictions = result.ExercisePredictions.Where(p => ids.Contains(p.AthleteId)).ToArray(),
            Frames = result.Frames.Select(f => f with
            {
                Athletes = f.Athletes.Where(a => ids.Contains(a.AthleteId)).ToArray(),
                Objects = f.Objects.Where(o => o.AthleteId is {} id && ids.Contains(id)).ToArray(),
                Shafts = f.Shafts?.Where(s => s.AthleteId is {} id && ids.Contains(id)).ToArray(),
                Shaft = f.Shaft?.AthleteId is {} owner && ids.Contains(owner) ? f.Shaft : null
            }).ToArray()
        };
    }
}
