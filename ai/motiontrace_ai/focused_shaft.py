"""Moving internal crops around confirmed pairs; all returned coordinates are global."""
import numpy as np
from .multi_shaft_tracking import _compatible, _gap, _groups


class FocusedShaftDetector:
    def __init__(self, detector):
        self.detector=detector
        self.regions={}
        self.time=0.
        self.poses={}
        self.statistics=dict(localCalls=0,localAccepted=0,fullCalls=0)

    def prepare(self,timestamp,poses,observations):
        self.time=timestamp
        previous_poses=self.poses
        self.poses={p['athleteId']:p for p in poses if p['trackingState']=='Tracked'}
        for observation in observations:
            owner=observation.get('athleteId')
            if owner is None or owner not in self.poses:continue
            previous=self.regions.get(owner,{})
            b=previous_poses.get(owner,self.poses[owner])['boundingBox']
            self.regions[owner]=dict(observation=observation,seen=timestamp,
                                    box=previous.get('box'),body=np.array([b['x'],b['y'],b['x']+b['width'],b['y']+b['height']]))
        self.regions={k:v for k,v in self.regions.items() if timestamp-v['seen']<=.75}

    def _crop(self,owner,region,width,height):
        pose=self.poses.get(owner)
        if pose is None:return None
        b=pose['boundingBox'];body=np.array([b['x'],b['y'],b['x']+b['width'],b['y']+b['height']])
        lines=[dict(line=[s['x1'],s['y1'],s['x2'],s['y2']],confidence=region['observation']['confidence'])
               for s in region['observation']['segments']]
        # Predict translation from the CURRENT person box, including walking backwards.
        if region['body'] is not None:
            shift=(body[:2]+body[2:]-region['body'][:2]-region['body'][2:])/2
            for line in lines:line['line']=(np.array(line['line'])+np.tile(shift,2)).tolist()
        points=np.array([s['line'] for s in lines]).reshape(-1,2)
        low=np.minimum(body[:2],points.min(axis=0));high=np.maximum(body[2:],points.max(axis=0))
        padding=np.maximum((high-low)*.2,[width*.035,height*.035])
        padding*=1+min(2,(self.time-region['seen'])*3)
        target=np.r_[low-padding,high+padding]
        old=region['box']
        if old is not None:
            smooth=old*.65+target*.35
            # Expand immediately to contain the moving subject; shrink gradually.
            target=np.r_[np.minimum(smooth[:2],target[:2]),np.maximum(smooth[2:],target[2:])]
        target=np.clip(target,[0,0,0,0],[width,height,width,height])
        region['box']=target
        return np.r_[np.floor(target[:2]),np.ceil(target[2:])].astype(int),lines

    def detect(self,image):
        height,width=image.shape[:2]
        # Keep discovery at its existing cadence: a new second lifter must have
        # enough consecutive observations to confirm a pair, not isolated scans.
        detected=self.detector.detect(image)
        self.statistics['fullCalls']+=1
        replacements=[]
        for owner,region in self.regions.items():
            crop=self._crop(owner,region,width,height)
            if crop is None:continue
            (x1,y1,x2,y2),expected=crop
            if x2-x1<64 or y2-y1<64 or (x2-x1)*(y2-y1)>=width*height*.9:continue
            local=self.detector.detect(image[y1:y2,x1:x2])
            self.statistics['localCalls']+=1
            translated=[dict(line=(np.array(s['line'])+[x1,y1,x1,y1]).tolist(),confidence=s['confidence']) for s in local]
            candidates=[g for g in _groups(translated,height) if _compatible(expected,g,height,.025)]
            candidates.sort(key=lambda g:_gap(expected,g))
            if not candidates or (len(candidates)>1 and _gap(expected,candidates[1])-_gap(expected,candidates[0])<height*.012):continue
            chosen=candidates[0]
            # Local evidence must agree with an existing full-frame detection.
            # Otherwise it could recover a rack/background bar inside the crop.
            agreeing=[s for s in detected if _compatible([s],chosen,height,.012)]
            if not agreeing:continue
            # Do not replace a clear long bar by a smaller fragment after zooming.
            span=lambda group:sum(np.linalg.norm(np.subtract(s['line'][2:],s['line'][:2])) for s in group)
            if span(chosen)<span(agreeing)*.8:continue
            replacements.append((agreeing,chosen))
        used=set()
        result=[]
        for agreeing,chosen in replacements:
            ids={id(s) for s in agreeing}
            if ids & used:continue
            used.update(ids);result.extend(chosen)
            self.statistics['localAccepted']+=1
        return [s for s in detected if id(s) not in used]+result
