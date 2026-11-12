using MotionTrace.Core.Athletes;

namespace MotionTrace.Core.Motion;

/// <summary>Keep wrist phase timing, require continuous upward shaft evidence from the same owner/track.</summary>
public static class ShaftRepGate
{
    public static MovementAnalysis Apply(MovementAnalysis candidates,IReadOnlyList<PoseFrame> frames,int athleteId,int height,CancellationToken token=default)
    {
        if (frames.Any(f => f.Objects.Count > 0)) return ApplyObjects(candidates, frames, athleteId, height, token);
        var accepted=new List<MovementRep>();
        foreach(var rep in candidates.Reps)
        {
            token.ThrowIfCancellationRequested();
            double travel=0,duration=0,lastTime=-1;int track=-1,count=0,ownerSupport=0;bool confirmed=false;
            foreach(var frame in frames)
            {
                if(frame.TimestampSeconds<rep.Lifting.Start)continue;
                if(frame.TimestampSeconds>rep.Lifting.End)break;
                var s=frame.ShaftForAthlete(athleteId);
                bool valid=s is {MotionReliable:true,Confidence:>=.5} && (s.AthleteId==null || s.AthleteId==athleteId) &&
                    frame.TimestampSeconds-s.DeltaSeconds>=rep.Lifting.Start-.001;
                if(!valid){travel=0;duration=0;count=0;ownerSupport=0;track=-1;continue;}
                if(s!.TrackId!=track || frame.TimestampSeconds-lastTime>.15){travel=0;duration=0;count=0;ownerSupport=0;}
                track=s.TrackId;lastTime=frame.TimestampSeconds;
                travel-=s.DeltaY;duration+=s.DeltaSeconds;count++;
                if(s.AthleteId==athleteId)ownerSupport++;
                if(count>=3 && ownerSupport>=2 && duration>=.12 && travel>=height*.004){confirmed=true;break;}
            }
            if(confirmed)accepted.Add(rep with {Number=accepted.Count+1});
        }
        return candidates with {Reps=accepted,Note=$"{accepted.Count} shaft-confirmed reps; {candidates.Reps.Count-accepted.Count} wrist candidates without confirmation. Timing and velocity use the wrist (px/s). Experimental bench model."};
    }

    private static MovementAnalysis ApplyObjects(MovementAnalysis candidates, IReadOnlyList<PoseFrame> frames,
        int athleteId, int height, CancellationToken token)
    {
        var samples = new ObjectTrajectoryProvider().Extract(frames, athleteId, Joint.LeftWrist, token);
        var reps = new List<MovementRep>();
        foreach (var rep in candidates.Reps)
        {
            token.ThrowIfCancellationRequested();
            var groups = samples.Where(s => s.Confidence >= .5 && s.TimestampSeconds >= rep.Lifting.Start &&
                s.TimestampSeconds <= rep.Lifting.End).GroupBy(s => s.ContinuityId);
            if (groups.Any(g => g.Count() >= 4 && g.Last().TimestampSeconds - g.First().TimestampSeconds >= .12 &&
                g.First().Position.Y - g.Last().Position.Y >= height * .004))
                reps.Add(rep with { Number = reps.Count + 1 });
        }
        return candidates with { Reps = reps, Note = $"{reps.Count} object-motion-confirmed reps. Timing and velocity use the wrist (px/s); object localization may be a proxy." };
    }
}
