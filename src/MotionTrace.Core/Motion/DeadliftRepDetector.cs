namespace MotionTrace.Core.Motion;

internal static class DeadliftRepDetector
{
    public static void Detect(List<MovementPoint> points,double travel,List<MovementRep> reps,CancellationToken token)
    {
        if(points.Count<5)return;
        int state=0,bottom=0,top=0,liftStart=0,loweringStart=0,topRest=0;
        double epsilon=travel*.12;
        MovementPhase Phase(int a,int b,bool up)=>new(points[a].Time,points[b].Time,new SampleRange<MovementPoint>(points,a,b-a+1),up);
        for(int i=1;i<points.Count;i++)
        {
            token.ThrowIfCancellationRequested();
            if(state==0)
            {
                if(points[i].Y>=points[bottom].Y)bottom=i;
                if(points[bottom].Y-points[i].Y>=travel && points[i].Time-points[bottom].Time>=.18)
                {liftStart=bottom;top=i;state=1;}
            }
            else if(state==1)
            {
                if(points[i].Y<points[top].Y-epsilon)top=i;
                bool stopped=points[i].Time-points[top].Time>=.35 && Math.Abs(points[i].Velocity)<=travel*.5;
                bool descending=points[i].Y-points[top].Y>=travel;
                if((stopped||descending) && points[top].Time-points[liftStart].Time>=.2)
                {
                    liftStart=LiftAnchor(points,liftStart,top,travel);
                    reps.Add(new(reps.Count+1,null,Phase(liftStart,top,true)));
                    topRest=top;state=2;i=top;
                }
            }
            else if(state==2)
            {
                if(points[i].Y<=points[top].Y+epsilon)topRest=i;
                if(points[i].Y-points[topRest].Y>=travel && points[i].Time-points[topRest].Time>=.18)
                {loweringStart=topRest;bottom=i;state=3;}
            }
            else
            {
                if(points[i].Y>points[bottom].Y)bottom=i;
                bool stopped=points[i].Time-points[bottom].Time>=.35 && Math.Abs(points[i].Velocity)<=travel*.5;
                bool rising=points[bottom].Y-points[i].Y>=travel;
                double descent=points[bottom].Y-points[loweringStart].Y;
                if((stopped||rising) && descent>=Math.Max(travel,(points[liftStart].Y-points[top].Y)*.7))
                {
                    // The descent belongs to the preceding lift, never to the next repetition.
                    reps[^1]=reps[^1] with {Lowering=Phase(loweringStart,bottom,false)};
                    state=0;i=bottom;
                }
            }
        }
    }

    private static int LiftAnchor(List<MovementPoint> points,int start,int top,double travel)
    {
        // Taking slack out of the bar can move it before the pull. Only a sustained
        // rest near floor level may replace the start; a sticking point higher up cannot.
        double floor=points[start].Y;
        double floorBand=Math.Max(travel*.5,(floor-points[top].Y)*.08);
        int anchor=start,quietStart=start;
        for(int i=start+1;i<top;i++)
        {
            if(points[i].Y<floor-floorBand || Math.Abs(points[i].Velocity)>travel*.5)
            {quietStart=i;continue;}
            if(points[i].Time-points[quietStart].Time>=.15)anchor=i;
        }
        return anchor;
    }
}
