"""Detector anchored LK tracking. Detection jumps never count as measured motion."""
import cv2
import numpy as np

def flow(previous,current,mask,minimum=3):
    points=cv2.goodFeaturesToTrack(previous,100,.01,4,mask=mask,blockSize=3)
    if points is None or len(points)<minimum:return None
    moved,ok,_=cv2.calcOpticalFlowPyrLK(previous,current,points,None,winSize=(21,21),maxLevel=3)
    if moved is None:return None
    back,ok2,_=cv2.calcOpticalFlowPyrLK(current,previous,moved,None,winSize=(21,21),maxLevel=3)
    if back is None:return None
    good=(ok[:,0]>0)&(ok2[:,0]>0)&(np.linalg.norm(back[:,0]-points[:,0],axis=1)<1)
    delta=moved[:,0]-points[:,0];delta=delta[good]
    if len(delta)<minimum:return None
    median=np.median(delta,axis=0);delta=delta[np.linalg.norm(delta-median,axis=1)<1.5]
    return np.median(delta,axis=0) if len(delta)>=minimum else None

def distance(point,line):
    a=np.array(line[:2]);b=np.array(line[2:]);p=np.array(point)
    u=np.clip(np.dot(p-a,b-a)/max(1,np.dot(b-a,b-a)),0,1)
    return float(np.linalg.norm(p-a-u*(b-a)))

def lying_lifter_near_bar(segments,poses,height):
    # Weaker torso evidence may rule OUT a spotter, but never assigns ownership.
    for p in poses:
        if p.get('trackingState')!='Tracked':continue
        joints=p['keypoints']
        shoulders=[k for k in joints if k['joint'] in ('LeftShoulder','RightShoulder') and k['confidence']>=.25]
        hips=[k for k in joints if k['joint'] in ('LeftHip','RightHip') and k['confidence']>=.25]
        wrists=[k for k in joints if k['joint'] in ('LeftWrist','RightWrist') and k['confidence']>=.4]
        if not shoulders or not hips or not wrists:continue
        sy=np.mean([k['y'] for k in shoulders])
        dx=abs(np.mean([k['x'] for k in hips])-np.mean([k['x'] for k in shoulders]))
        dy=abs(np.mean([k['y'] for k in hips])-sy)
        if dx>max(height*.025,dy*1.5) and np.mean([k['y'] for k in wrists])<=sy+height*.015 and min(distance((k['x'],k['y']),s['line']) for k in wrists for s in segments)<height*.12:
            return True
    return False


def associate(segments,poses,height,bench_only=False):
    candidates=[];bench_context=bench_only or lying_lifter_near_bar(segments,poses,height)
    for p in poses:
        if p.get('trackingState')!='Tracked':continue
        wrists=[k for k in p['keypoints'] if k['joint'] in ('LeftWrist','RightWrist') and k['confidence']>=.4]
        if not wrists or (len(wrists)==1 and wrists[0]['confidence']<.6):continue
        shoulders=[k for k in p['keypoints'] if k['joint'] in ('LeftShoulder','RightShoulder') and k['confidence']>=.4]
        if not shoulders:continue
        wrist_y=np.mean([k['y'] for k in wrists])
        shoulder_y=np.mean([k['y'] for k in shoulders])
        hips=[k for k in p['keypoints'] if k['joint'] in ('LeftHip','RightHip') and k['confidence']>=.4]
        bench=wrist_y<=shoulder_y+height*.015
        score=float(np.mean([min(distance((k['x'],k['y']),s['line']) for s in segments) for k in wrists]))
        # A standing pull has two hands below the hips, unlike a bench spotter
        # reaching down from above. These are ownership cues, not exercise labels.
        deadlift=len(wrists)==2 and len(hips)==2 and shoulder_y<np.mean([k['y'] for k in hips])-height*.03 and wrist_y>=np.mean([k['y'] for k in hips])-height*.025
        squat=len(wrists)==2 and hips and shoulder_y<np.mean([k['y'] for k in hips])-height*.03 and abs(wrist_y-shoulder_y)<height*.06 and min(distance((k['x'],k['y']),s['line']) for k in shoulders for s in segments)<height*.035
        if not (bench or deadlift or squat):continue
        if score<height*(.025 if len(wrists)==1 else .045):candidates.append((score,p['athleteId'],bench))
    # A standing bench spotter can also have hands below their hips. A nearby
    # lying lifter rules out that deadlift cue instead of switching ownership.
    if bench_context:candidates=[c for c in candidates if c[2]]
    candidates.sort()
    if not candidates or (len(candidates)>1 and candidates[1][0]-candidates[0][0]<height*.012):return None
    return candidates[0][1]

def compatible_fragments(previous,current,height):
    """Allow a different exposed part on the same line, but reject another bar."""
    if not previous or not current:return False
    a=max(previous,key=lambda s:np.linalg.norm(np.array(s['line'][2:])-s['line'][:2]))['line']
    av=np.array(a[2:])-a[:2];length=np.linalg.norm(av)
    if length<8:return False
    for s in current:
        b=s['line'];bv=np.array(b[2:])-b[:2];bl=np.linalg.norm(bv)
        if bl<8 or abs(np.dot(av,bv))/(length*bl)<.985:continue
        mid=(np.array(b[:2])+b[2:])/2
        perpendicular=abs(np.cross(av,mid-a[:2]))/length
        # Bound longitudinal displacement too: parallel bars far away are distinct.
        gap=min(distance(b[:2],a),distance(b[2:],a),distance(a[:2],b),distance(a[2:],b))
        if perpendicular<=height*.015 and gap<=height*.12:return True
    return False


class ShaftTracker:
    VERSION='shaft-lk-4'
    def __init__(self,detector):
        self.detector=detector;self.previous=None;self.time=None;self.last_detection=-1.;self.segments=[];self.track_id=0;self.previous_poses=[]
        self.last_confirmed=-1.;self.last_observation=[];self.last_owner=None
        self.bench_until=-1.

    def update(self,image,timestamp,poses):
        h,w=image.shape[:2];scale=640/max(h,w)
        def owner_of(segments):
            if lying_lifter_near_bar(segments,poses,h):self.bench_until=timestamp+2
            return associate(segments,poses,h,bench_only=timestamp<=self.bench_until)
        gray=cv2.cvtColor(cv2.resize(image,(round(w*scale),round(h*scale))),cv2.COLOR_BGR2GRAY)
        dt=timestamp-self.time if self.time is not None else 0
        shift=camera=None;reliable=False
        if self.previous is not None and self.previous.shape==gray.shape and 0<dt<=.15 and self.segments:
            mask=np.zeros_like(gray)
            for s in self.segments:
                x1,y1,x2,y2=np.round(np.array(s['line'])*scale).astype(int)
                cv2.line(mask,(x1,y1),(x2,y2),255,7)
            shift=flow(self.previous,gray,mask)
            background=np.full_like(gray,255)
            for p in self.previous_poses:
                b=p['boundingBox'];x,y=b['x']*scale,b['y']*scale
                cv2.rectangle(background,(int(x)-8,int(y)-8),(int(x+b['width']*scale)+8,int(y+b['height']*scale)+8),0,-1)
            background[cv2.dilate(mask,np.ones((25,25),np.uint8))>0]=0
            camera=flow(self.previous,gray,background,minimum=8)
            if shift is not None and np.linalg.norm(shift)<640*.08:
                for s in self.segments:s['line']=(np.array(s['line'])+np.tile(shift/scale,2)).tolist()
                reliable=camera is not None
            else:
                self.segments=[];shift=None
        elif self.previous is not None:
            self.segments=[]
        if not self.segments or timestamp-self.last_detection>=.1:
            detected=self.detector.detect(image);self.last_detection=timestamp
            # Group collinear fragments; multiple distinct candidates remain ambiguous.
            groups=[]
            for s in sorted(detected,key=lambda s:-np.linalg.norm(np.array(s['line'][:2])-s['line'][2:])):
                line=np.array(s['line']);mid=(line[:2]+line[2:])/2
                placed=False
                for group in groups:
                    ref=np.array(group[0]['line']);v=ref[2:]-ref[:2];u=line[2:]-line[:2]
                    perpendicular=abs(np.cross(v,mid-ref[:2]))/max(1,np.linalg.norm(v))
                    aligned=abs(np.dot(v,u))/max(1,np.linalg.norm(v)*np.linalg.norm(u))>.94
                    if perpendicular<h*.015 and aligned:group.append(s);placed=True;break
                if not placed:groups.append([s])
            if self.segments:
                groups.sort(key=lambda g:np.mean([min(distance((np.array(s['line'][:2])+s['line'][2:])/2,r['line']) for r in self.segments) for s in g]))
                if groups:
                    gap=np.mean([min(distance((np.array(s['line'][:2])+s['line'][2:])/2,r['line']) for r in self.segments) for s in groups[0]])
                    if gap>h*.04:self.segments=[];reliable=False
            elif len(groups)>1:
                # Prefer the only group associated with a pair of wrists; otherwise no lock.
                associated=[g for g in groups if owner_of(g) is not None]
                groups=associated if len(associated)==1 else []
            if groups:
                chosen=groups[0]
                owner=owner_of(chosen)
                if not self.segments:
                    same=timestamp-self.last_confirmed<=.15 and compatible_fragments(self.last_observation,chosen,h) and (owner is None or self.last_owner is None or owner==self.last_owner)
                    if not same:self.track_id+=1
                    reliable=False
                self.segments=chosen;self.last_confirmed=timestamp
            elif self.segments and shift is not None and timestamp-self.last_confirmed<=.15:
                # LK supports the short detector miss, but it is not a fresh observation.
                reliable=False
            else:self.segments=[];reliable=False
        self.previous=gray;self.time=timestamp;self.previous_poses=poses
        if not self.segments:return None
        for s in self.segments:
            s['line']=[float(np.clip(v,0,w if i%2==0 else h)) for i,v in enumerate(s['line'])]
        owner=owner_of(self.segments)
        self.last_observation=[dict(line=list(s['line']),confidence=s['confidence']) for s in self.segments];self.last_owner=owner
        delta=(shift-camera)/scale if reliable else np.zeros(2)
        return dict(trackId=self.track_id,athleteId=owner,
                    segments=[dict(x1=s['line'][0],y1=s['line'][1],x2=s['line'][2],y2=s['line'][3]) for s in self.segments],
                    confidence=float(np.mean([s['confidence'] for s in self.segments])),
                    motionReliable=bool(reliable),deltaY=float(delta[1]),deltaSeconds=dt if reliable else 0)
