using MotionTrace.Core.Athletes;
using MotionTrace.Core.Analysis;

namespace MotionTrace.Tests;

public class AthleteSelectionTests
{
    [Fact] public void SelectAllCannotReintroduceBackgroundTracks()
    {
        var result = AnalysisWithParticipants(false, true, false, true);
        var selection = new AthleteSelection(AnalysisSelection.ParticipantIds(result));
        selection.SetAllSelected(false);
        selection.SetAllSelected(true);
        Assert.False(selection.Contains(1));
        Assert.True(selection.Contains(2));
        Assert.False(selection.Contains(3));
        Assert.True(selection.Contains(4));
    }

    [Fact] public void NoConfirmedParticipantProducesNoSelectionCandidates()
    {
        Assert.Empty(AnalysisSelection.ParticipantIds(AnalysisWithParticipants(false, false)));
    }

    [Fact] public void ExportRejectsBackgroundTracksEvenWhenCallerSelectsThem()
    {
        var result = AnalysisWithParticipants(false, true);
        var exported = AnalysisSelection.Filter(result, new HashSet<int> { 1, 2 });
        Assert.Equal(2, Assert.Single(exported.Athletes).Id);
        Assert.Equal(2, Assert.Single(exported.Frames[0].Athletes).AthleteId);
        Assert.Equal(2, Assert.Single(exported.Frames[0].Objects).AthleteId);
        Assert.Equal(2, result.Athletes.Count);
        Assert.Equal(2, result.Frames[0].Athletes.Count);
    }

    private static AnalysisResult AnalysisWithParticipants(params bool[] participants)
    {
        var athletes = participants.Select((participant, index) => new AthleteTrack(index + 1, $"Athlete {index + 1}")
            { IsExerciseParticipant = participant }).ToArray();
        return new(4, new("test.mp4", 1, 100, 100, 30), new("test", "test", "test"), athletes,
            [new(0, athletes.Select(a => new AthletePose(a.Id, new(0, 0, 10, 10), 1, [])).ToArray())
            {
                Objects = athletes.Select(a => new TrackedObject($"bar-{a.Id}", a.Id, new(0, 0, 10, 10),
                    null, 1, TrackingState.Tracked, null)).ToArray()
            }], []);
    }

    [Fact] public void EmptySelectionCannotBeCreated() => Assert.Throws<ArgumentException>(() => new AthleteSelection([]));
    [Fact] public void LastAthleteRemainsSelectedAndSelectionCanBeTransferred()
    {
        var selection = new AthleteSelection([1, 2]);
        Assert.True(selection.TrySetSelected(1, false));
        Assert.False(selection.TrySetSelected(2, false));
        Assert.True(selection.Contains(2));
        Assert.True(selection.TrySetSelected(1, true));
        Assert.True(selection.TrySetSelected(2, false));
    }
    [Fact] public void BulkSelectionRestoresAllAvailableAthletesAfterIndividualChanges()
    {
        var selection = new AthleteSelection([1, 1, 2]);
        selection.SetAllSelected(false);
        Assert.True(selection.Contains(1));Assert.False(selection.Contains(2));
        selection.TrySetSelected(2,true);
        selection.TrySetSelected(1,false);
        Assert.False(selection.Contains(1));Assert.True(selection.Contains(2));
        selection.SetAllSelected(true);
        Assert.True(selection.Contains(1));Assert.True(selection.Contains(2));
    }
    [Fact] public void UnknownIdIsRejected() => Assert.Throws<ArgumentOutOfRangeException>(() => new AthleteSelection([1]).TrySetSelected(2, true));
}
