using MotionTrace.Core.Athletes;
using MotionTrace.Core.Exercise;
namespace MotionTrace.Tests;
public class BenchPressTests
{
    private static PoseFrame[] Sequence(bool standing=false, bool moving=true, double confidence=.9) =>
        Enumerable.Range(0,61).Select(i => {
            double phase=moving ? (1+Math.Sin(i*.1*Math.PI))/2 : .5;
            double theta=.05+1.2*phase;
            Keypoint K(Joint j,double x,double y)=>new(j,new(x,y),confidence);
            var keys=new[]{ K(Joint.LeftShoulder,100,200), K(Joint.LeftHip,standing?100:200,standing?300:200),
                K(Joint.LeftElbow,100+60*Math.Cos(theta),200+60*Math.Sin(theta)), K(Joint.LeftWrist,100,90+40*phase) };
            return new PoseFrame(i*.1,[new(1,new(0,0,300,400),.9,keys)]);
        }).ToArray();
    [Fact] public void RecliningArmCyclesAreCandidateBenchPress() => Assert.Equal(ExerciseType.BenchPress,new BenchPressClassifier().Classify(Sequence(),1).ExerciseType);
    [Fact] public void StandingSpotterIsUnknown() => Assert.Equal(ExerciseType.Unknown,new BenchPressClassifier().Classify(Sequence(standing:true),1).ExerciseType);
    [Fact] public void StaticSetupIsUnknown() => Assert.Equal(ExerciseType.Unknown,new BenchPressClassifier().Classify(Sequence(moving:false),1).ExerciseType);
    [Fact] public void WeakPoseIsUnknown() => Assert.Equal(ExerciseType.Unknown,new BenchPressClassifier().Classify(Sequence(confidence:.1),1).ExerciseType);
    [Fact] public void DoesNotUseAnotherPerson() => Assert.Equal(ExerciseType.Unknown,new BenchPressClassifier().Classify(Sequence(),2).ExerciseType);
    [Fact] public void MissingIntervalIsNotMovement() => Assert.Equal(ExerciseType.Unknown,new BenchPressClassifier().Classify(Sequence().Where(f=>f.TimestampSeconds<2 || f.TimestampSeconds>4).ToArray(),1).ExerciseType);
}
