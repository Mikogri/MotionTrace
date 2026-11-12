using MotionTrace.Core.Exercise;
namespace MotionTrace.Core.Motion;
internal static class MovementRepDetector
{
    public static void Detect(List<MovementPoint> p, ExerciseType exercise, double travel, List<MovementRep> reps, CancellationToken token)
    {
        if(exercise==ExerciseType.Deadlift){DeadliftRepDetector.Detect(p,travel,reps,token);return;}
        if (p.Count < 5) return;
        double epsilon=travel*.12;
        int state=0, top=0, bottom=0, start=0, riseStart=0, high=0, bottomLast=0;
        bool noLowering=false;
        double topLevel=p[0].Y, bottomLevel=p[0].Y;
        for (int i=1;i<p.Count;i++)
        {
            token.ThrowIfCancellationRequested();
            if(state==0)
            {
                // The latest point near the top anchors the drop; small oscillations don't start a rep.
                topLevel=Math.Min(topLevel,p[i].Y);
                bottomLevel=Math.Max(bottomLevel,p[i].Y);
                if(p[i].Y<=topLevel+epsilon) top=i;
                if(p[i].Y>=bottomLevel-epsilon) bottom=i;
                if(p[i].Y-p[top].Y>=travel && p[i].Time-p[top].Time>=.18)
                { start=RestAnchor(p,top,i,travel,true); bottom=bottomLast=i; state=1; noLowering=false; }
                else if(exercise==ExerciseType.Deadlift && p[bottom].Y-p[i].Y>=travel && p[i].Time-p[bottom].Time>=.18)
                { riseStart=bottom; high=i; state=2; noLowering=true; }
            }
            else if(state==1)
            {
                if(p[i].Y>p[bottom].Y) { bottom=i; bottomLast=i; }
                else if(Math.Abs(p[i].Y-p[bottom].Y)<=epsilon) bottomLast=i;
                if(p[bottom].Y-p[i].Y>=travel && p[i].Time-p[bottomLast].Time>=.18)
                { riseStart=RiseAnchor(p,bottom,bottomLast,travel); high=i; state=2; }
            }
            else
            {
                if(p[i].Y<p[high].Y-epsilon) high=i;
                // Refine against the completed stroke: setup can exceed the initial threshold.
                // Only a rest near the returned lockout qualifies, not a mid-descent pause.
                int refinedStart=noLowering?start:DropAnchor(p,start,bottom,high,travel);
                double rise=p[riseStart].Y-p[high].Y;
                bool enough=rise>=travel && p[high].Time-p[riseStart].Time>=.20 &&
                    (noLowering || rise>=.70*(p[bottom].Y-p[refinedStart].Y));
                bool stopped=p[i].Time-p[high].Time>=.35 && Math.Abs(p[i].Velocity)<=travel*.5;
                bool reversed=p[i].Y-p[high].Y>=travel;
                // After a full return to lockout, racking can begin with a small
                // sustained reversal before visibility is lost. Requiring another full
                // descent here discards the completed final rep. Never apply this to a
                // partial press or carry confirmation across a visibility gap.
                bool racking = !noLowering && p[high].Y <= p[refinedStart].Y + epsilon &&
                    p[i].Y - p[high].Y >= travel * .2 && p[i].Time - p[high].Time >= .2 &&
                    SustainedDownwardMotion(p, high, i, travel);
                if(enough && (stopped || reversed || racking))
                {
                    MovementPhase Phase(int a,int b,bool up)=>new(p[a].Time,p[b].Time,new SampleRange<MovementPoint>(p,a,b-a+1),up);
                    var down=noLowering?null:Phase(refinedStart,bottom,false);
                    if(down is null || down.Duration>=.18)
                        reps.Add(new(reps.Count+1,down,Phase(riseStart,high,true)) { PreparationStart=down is null?null:p[PreparationAnchor(p,start,reps)].Time });
                    state=0; top=bottom=high;
                    topLevel=bottomLevel=p[high].Y;
                    // Replay the confirmation interval so a fast following descent isn't lost.
                    i=high;
                }
                else if(reversed && !enough)
                {
                    // A partial press followed by another descent is not a completed rep.
                    state=1; bottom=bottomLast=i; noLowering=false; start=high;
                }
            }
        }
    }

    private static bool SustainedDownwardMotion(List<MovementPoint> points,int high,int current,double travel)
    {
        int start=current;
        while(start>high && points[current].Time-points[start].Time<.1)start--;
        if(points[current].Time-points[start].Time<.1)return false;
        for(int i=start;i<=current;i++)if(points[i].Velocity<travel*.15)return false;
        return true;
    }

    private static int RiseAnchor(List<MovementPoint> points,int bottom,int lastNearBottom,double travel)
    {
        // Proximity to the bottom is not a pause: slow upward motion must count as lifting.
        int start=lastNearBottom;
        while(start>bottom && points[start-1].Velocity < -travel*.15)start--;
        return start;
    }

    private static int PreparationAnchor(List<MovementPoint> p,int start,List<MovementRep> reps)
    {
        // Between reps, preparation begins at the previous lockout. On the first rep,
        // include the preceding unrack movement, stopping at a sustained rest.
        if(reps.Count>0) {
            int a=start;while(a>0 && p[a-1].Time>=reps[^1].End)a--;return a;
        }
        int anchor=start;double quiet=0;
        for(int i=start-1;i>=0 && p[start].Time-p[i].Time<8;i--) {
            if(Math.Abs(p[i].Velocity)<3)quiet+=p[i+1].Time-p[i].Time;else quiet=0;
            if(quiet>=.3)break;
            anchor=i;
        }
        return anchor;
    }
    private static int DropAnchor(List<MovementPoint> p,int start,int bottom,int high,double travel)
    {
        double range=p[bottom].Y-p[high].Y;
        double ceiling=p[high].Y+Math.Max(travel,range*.35);
        double peak=0;
        for(int i=start;i<=bottom;i++)if(p[i].Y<=ceiling)peak=Math.Max(peak,p[i].Velocity);
        double threshold=Math.Max(travel*.5,peak*.22);
        start=RestAnchor(p,start,bottom,travel,true,ceiling);
        // A sustained descent replaces slow setup drift; do not re-anchor halfway down.
        for(int i=start;i<bottom;i++) {
            if(p[i].Y>ceiling || p[i].Velocity<threshold)continue;
            int end=i;while(end<bottom && p[end].Time-p[i].Time<.18 && p[end].Velocity>=threshold*.6)end++;
            if(p[end].Time-p[i].Time<.15 || p[end].Y-p[i].Y<travel*.3)continue;
            int onset=i;
            while(onset>start && p[onset-1].Velocity>threshold*.3 && p[i].Time-p[onset-1].Time<.25)onset--;
            return onset;
        }
        return RestAnchor(p,start,bottom,travel,true,ceiling);
    }

    private static int RestAnchor(List<MovementPoint> points,int original,int end,double travel,bool downward,double maximumY=double.PositiveInfinity)
    {
        int anchor=original,quietStart=original;
        for(int i=original+1;i<=end;i++)
        {
            if(Math.Abs(points[i].Velocity)>travel*.5){quietStart=i;continue;}
            double displacement=downward?points[end].Y-points[i].Y:points[i].Y-points[end].Y;
            if(points[i].Time-points[quietStart].Time>=.15 && points[end].Time-points[i].Time>=.18 && displacement>=travel*.35 && points[i].Y<=maximumY)
                anchor=i;
        }
        return anchor;
    }
}
