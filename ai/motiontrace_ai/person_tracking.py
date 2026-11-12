"""Detector-only association. Appearance descriptor is a replaceable weak cue, not ReID."""
from dataclasses import dataclass, field
import math
from .tracking import overlap

@dataclass
class Identity:
    identity: int
    box: list
    time: float
    appearance: list = field(default_factory=list)
    velocity: tuple = (0., 0.)
    hits: int = 1
    state: str = 'Tracked'
    confidence: float = 1.

class PersonTracker:
    VERSION = 'conservative-box-2'
    def __init__(self, maximum_lost_seconds=1.0, ambiguity_margin=.08):
        self.maximum_lost_seconds=maximum_lost_seconds
        self.ambiguity_margin=ambiguity_margin
        self.tracks=[]
        self.next_id=1
        self.confirmed=set()
        self.last_time=-1

    def cost(self, track, detection, time):
        box=detection['box']; old=track.box; dt=time-track.time
        # After the ordinary matching window, stale detector-box velocity can
        # project a stationary, occluded lifter far away. Strict reacquisition
        # compares the last observation instead of extrapolating that jitter.
        prediction_time=min(dt,.4) if dt<=self.maximum_lost_seconds else 0.
        dx,dy=(v*prediction_time for v in track.velocity)
        predicted=[old[0]+dx,old[1]+dy,old[2]+dx,old[3]+dy]
        diagonal=max(1,math.hypot(old[2]-old[0],old[3]-old[1]))
        distance=math.hypot((predicted[0]+predicted[2]-box[0]-box[2])/2,(predicted[1]+predicted[3]-box[1]-box[3])/2)/diagonal
        iou=overlap(predicted,box)
        ratio=((box[2]-box[0])*(box[3]-box[1]))/max(1,(old[2]-old[0])*(old[3]-old[1]))
        appearance=detection.get('appearance',[])
        appearance_distance=sum(abs(a-b) for a,b in zip(track.appearance,appearance))/2 if track.appearance and appearance else 0
        if distance>.35 or ratio<.45 or ratio>2.2 or (iou<.1 and distance>.15) or appearance_distance>.5: return 1e6
        # Reacquisition needs appearance evidence, not just a person occupying an old box.
        if track.state=='Lost' and (not appearance or not track.appearance or appearance_distance>.25 or distance>.2): return 1e6
        # A brief detector occlusion must not split an established lifter, but the
        # weak histogram is only usable here together with strong spatial overlap.
        if dt>self.maximum_lost_seconds and (
            not appearance or len(appearance)!=len(track.appearance)
            or appearance_distance>.15 or iou<.5 or overlap(old,box)<.5
            or distance>.2
        ): return 1e6
        return .55*(1-iou)+.25*distance+.2*appearance_distance

    def update(self,detections,time):
        from scipy.optimize import linear_sum_assignment
        if not math.isfinite(time) or time<=self.last_time: raise ValueError('Timestamps must increase')
        self.last_time=time
        self.tracks=[t for t in self.tracks if time-t.time<=self.maximum_lost_seconds
                     or (t.hits>=3 and time-t.time<=2.)]
        assigned={}; blocked=set()
        if self.tracks and detections:
            costs=[[self.cost(t,d,time) for d in detections] for t in self.tracks]
            rows,cols=linear_sum_assignment(costs)
            for r,c in zip(rows,cols):
                cost=costs[r][c]
                if cost>.75: continue
                alternatives=[v for j,v in enumerate(costs[r]) if j!=c]+[costs[j][c] for j in range(len(costs)) if j!=r]
                if alternatives and min(alternatives)-cost<self.ambiguity_margin:
                    blocked.add(c); continue
                t=self.tracks[r];d=detections[c];dt=time-t.time
                velocity=tuple(((d['box'][k]+d['box'][k+2])-(t.box[k]+t.box[k+2]))/(2*dt) for k in (0,1))
                t.velocity=tuple(.7*a+.3*b for a,b in zip(t.velocity,velocity))
                t.box=d['box']; t.time=time; t.hits+=1; t.state='Tracked'; t.confidence=max(.1,1-cost)
                # Freeze appearance under overlaps to avoid learning the occluder.
                if d.get('appearance') and all(i==c or overlap(d['box'],other['box'])<.15 for i,other in enumerate(detections)):
                    t.appearance=[.95*a+.05*b for a,b in zip(t.appearance,d['appearance'])] if t.appearance else d['appearance']
                assigned[c]=t
        for i,d in enumerate(detections):
            if i not in assigned and i not in blocked and d['confidence']>=.6:
                # Don't spawn a duplicate directly on a currently ambiguous/lost identity.
                if any(overlap(t.box,d['box'])>.5 for t in self.tracks): continue
                t=Identity(self.next_id,d['box'],time,d.get('appearance',[])); self.next_id+=1;self.tracks.append(t);assigned[i]=t
        for t in self.tracks:
            if t.time!=time: t.state='Lost';t.confidence=0
            if t.hits>=3:self.confirmed.add(t.identity)
        return [(t,detections[i]) for i,t in assigned.items()], [t for t in self.tracks if t.state=='Lost' and t.identity in self.confirmed]

class StableCrop:
    def __init__(self,padding=.2,time_constant=.12):
        if not 0<=padding<=.5 or time_constant<=0: raise ValueError('Invalid crop configuration')
        self.padding=padding;self.time_constant=time_constant;self.history={}
    def update(self,identity,box,time,width,height):
        old,last=self.history.get(identity,(box,time))
        alpha=1-math.exp(-max(0,time-last)/self.time_constant) if time>last else 1
        smoothed=[a+alpha*(b-a) for a,b in zip(old,box)]
        self.history[identity]=(smoothed,time)
        # Include both boxes so smoothing cannot crop a fast limb/body translation.
        b=[min(smoothed[0],box[0]),min(smoothed[1],box[1]),max(smoothed[2],box[2]),max(smoothed[3],box[3])]
        px=(b[2]-b[0])*self.padding;py=(b[3]-b[1])*self.padding
        return [max(0,b[0]-px),max(0,b[1]-py),min(width,b[2]+px),min(height,b[3]+py)]

def appearance_descriptor(image,box):
    import cv2
    x1,y1,x2,y2=map(int,box)
    h,w=image.shape[:2];crop=image[max(0,y1):min(h,y2),max(0,x1):min(w,x2)]
    if not crop.size:return []
    hsv=cv2.cvtColor(cv2.resize(crop,(32,64)),cv2.COLOR_BGR2HSV)
    histogram=cv2.calcHist([hsv],[0,1],None,[8,4],[0,180,0,256]).flatten()
    return (histogram/max(1,histogram.sum())).tolist()
