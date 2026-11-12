using MotionTrace.Core.Exercise;

namespace MotionTrace.Tests;

public class TemporalAnalysisTests
{
    [Fact] public void BriefMotionDoesNotStartSet()
    {
        var state = new ExerciseStateMachine();
        Assert.Equal(ExerciseStatus.Waiting, state.Update(0, true));
        Assert.Equal(ExerciseStatus.Waiting, state.Update(0.1, false));
    }
    [Fact] public void PauseInsideRepDoesNotFinishSet()
    {
        var state = new ExerciseStateMachine();
        state.Update(0, true);
        Assert.Equal(ExerciseStatus.Performing, state.Update(0.4, true));
        for (int i = 2; i <= 6; i++) Assert.Equal(ExerciseStatus.Performing, state.Update(i * 0.4, false));
        Assert.Equal(ExerciseStatus.Performing, state.Update(2.8, true));
    }
    [Fact] public void SustainedRestFinishesAndNewMovementCanRestart()
    {
        var state = new ExerciseStateMachine();
        state.Update(0, true); state.Update(0.4, true);
        for (int i = 2; i <= 10; i++) state.Update(i * 0.4, false);
        Assert.Equal(ExerciseStatus.Finished, state.Status);
        state.Update(4.4, true);
        Assert.Equal(ExerciseStatus.Performing, state.Update(4.8, true));
    }
    [Fact] public void DetectionGapDoesNotCountAsRest()
    {
        var state = new ExerciseStateMachine();
        state.Update(0, true); state.Update(0.4, true); state.Update(0.5, false);
        Assert.Equal(ExerciseStatus.Performing, state.Update(10, false));
    }
    [Fact] public void OutOfOrderTimeIsRejected()
    {
        var state = new ExerciseStateMachine(); state.Update(1, false);
        Assert.Throws<ArgumentOutOfRangeException>(() => state.Update(1, true));
    }
    [Fact] public void RepTimeUsesTimestamps() => Assert.Equal(2.41, new Repetition(1, 1, 3.41).TotalSeconds, 6);
    [Fact] public void NegativeAndReversedRepIntervalsAreRejected()
    {
        Assert.Throws<ArgumentException>(() => new Repetition(0, 0, 1));
        Assert.Throws<ArgumentException>(() => new Repetition(1, 3, 1));
        Assert.Throws<ArgumentException>(() => new Repetition(1, double.NaN, 1));
    }
    [Fact] public void OverlappingPhasesAreRejected() => Assert.Throws<ArgumentException>(() =>
        new Repetition(1, 0, 3, [new(RepPhase.Eccentric, 0, 2), new(RepPhase.Concentric, 1, 3)]));
}
