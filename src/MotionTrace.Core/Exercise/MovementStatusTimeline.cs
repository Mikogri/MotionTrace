using MotionTrace.Core.Motion;
namespace MotionTrace.Core.Exercise;

public static class MovementStatusTimeline
{
    public static ExerciseStatus[] Build(IReadOnlyList<MovementPoint> samples,double duration,double minimumSpeed,CancellationToken token=default)
    {
        var machine=new ExerciseStateMachine();
        var states=new ExerciseStatus[(int)Math.Ceiling(duration*10)+1];
        for(int i=0;i<states.Length;i++)
        {
            token.ThrowIfCancellationRequested();
            double time=i/10.0;var sample=PlaybackSampleLookup.At(samples,time);
            // Missing data is never evidence of rest. The state machine resets its timers on a time gap.
            states[i]=sample is null?machine.Status:machine.Update(time,Math.Abs(sample.Velocity)>minimumSpeed);
        }
        return states;
    }
}
