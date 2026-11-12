"""Confirm person/bar pairs using anatomy and a short history of shared motion."""
from collections import deque
import numpy as np
from .shaft_tracking import associate, distance, lying_lifter_near_bar


class ShaftOwnership:
    VERSION = 'motion-pairs-1'

    def __init__(self):
        self.history = {}
        self.owners = {}
        self.bench_until = {}
        self.participants = set()
        self.camera = {}

    def update(self, timestamp, shafts, poses, height):
        self.camera = {k:v for k,v in self.camera.items() if timestamp-v[1] <= 2}
        self.history = {k:v for k,v in self.history.items() if timestamp-v[-1]['time'] <= 2}
        self.owners = {k:v for k,v in self.owners.items() if timestamp-v[1] <= .6}
        self.bench_until = {k:v for k,v in self.bench_until.items() if v >= timestamp}
        proposals = []
        frame = shafts  # Shared references allow bounded backfill of the first movement.
        for shaft in shafts:
            shaft['ownershipAmbiguous'] = False
            track = shaft['trackId']
            camera_y = self.camera.get(track,(0.,timestamp))[0]+shaft.get('cameraDeltaY',0.)
            self.camera[track] = camera_y,timestamp
            segments = [dict(line=[s['x1'],s['y1'],s['x2'],s['y2']]) for s in shaft['segments']]
            if lying_lifter_near_bar(segments, poses, height):
                self.bench_until[track] = timestamp+2
            candidates = []
            for pose in poses:
                athlete = pose['athleteId']
                if associate(segments, [pose], height, timestamp <= self.bench_until.get(track, -1)) is None:
                    continue
                wrists = [p for p in pose['keypoints'] if p['joint'] in ('LeftWrist','RightWrist') and p['confidence'] >= .4]
                # Use a consistent anatomical point; switching wrist visibility resets evidence.
                signature = tuple(sorted(p['joint'] for p in wrists))
                anchor = np.mean([[p['x'],p['y']] for p in wrists],axis=0)
                line = min(segments,key=lambda s:distance(anchor,s['line']))['line']
                a,b = np.array(line[:2]),np.array(line[2:])
                vector = b-a
                if abs(vector[0]) < .2*np.linalg.norm(vector):
                    continue  # Near-vertical projections cannot establish vertical co-motion.
                bar_y = a[1]+(anchor[0]-a[0])*vector[1]/vector[0]
                key = track, athlete
                history = self.history.setdefault(key, deque())
                if history and (timestamp-history[-1]['time'] > .2 or history[-1]['signature'] != signature):
                    history.clear()
                history.append(dict(time=timestamp,bar=float(bar_y-camera_y),anchor=float(anchor[1]-camera_y),
                                    measured=shaft['deltaY'] if shaft['motionReliable'] else 0.,
                                    signature=signature,shaft=shaft,frame=frame))
                while history and timestamp-history[0]['time'] > 3:
                    history.popleft()
                score = self._motion_score(history,height,timestamp)
                incumbent = self.owners.get(track)
                if incumbent and incumbent[0] == athlete:
                    score = max(score, 1.2)
                if score > 0:
                    candidates.append((score,athlete,history))
            incumbent=self.owners.get(track)
            if incumbent and not any(c[1]==incumbent[0] for c in candidates):
                owner_pose=next((p for p in poses if p['athleteId']==incumbent[0] and p['trackingState']=='Tracked'),None)
                # Once motion has confirmed the pair, obscured hands do not revoke it
                # while the same observed bar remains beside the same tracked body.
                if owner_pose and self._near_body(shaft,owner_pose,height):
                    candidates.append((1.2,incumbent[0],[dict(shaft=shaft,frame=frame)]))
            candidates.sort(key=lambda c:-c[0])
            if candidates and (len(candidates)==1 or candidates[0][0]-candidates[1][0] >= .12):
                proposals.append((candidates[0][0],track,*candidates[0][1:]))
            elif len(candidates)>1:
                shaft['ownershipAmbiguous'] = True

        # A person cannot own two bars in the same frame. Equally plausible bars stay unknown.
        proposals.sort(key=lambda p:-p[0])
        used = set()
        for score,track,athlete,history in proposals:
            if athlete in used:
                continue
            competing = [p for p in proposals if p[2]==athlete and p[1]!=track]
            if competing and score-max(p[0] for p in competing) < .12:
                next(s for s in shafts if s['trackId']==track)['ownershipAmbiguous']=True
                continue
            used.add(athlete)
            self.owners[track] = athlete,timestamp
            self.participants.add(athlete)
            for row in history:
                observation = row['shaft']
                if observation['athleteId'] is None and not observation.get('ownershipAmbiguous',False) and not any(
                    s is not observation and s['athleteId']==athlete for s in row['frame']
                ):
                    observation['athleteId'] = athlete
        return shafts

    @staticmethod
    def _near_body(shaft,pose,height):
        b=pose.get('boundingBox')
        if b is None:return False
        margin=height*.04
        return any(b['x']-margin<=(s['x1']+s['x2'])/2<=b['x']+b['width']+margin and
                   b['y']-margin<=(s['y1']+s['y2'])/2<=b['y']+b['height']+margin for s in shaft['segments'])

    @staticmethod
    def _motion_score(history,height,timestamp):
        rows = [r for r in history if timestamp-r['time'] <= 1.5]
        if len(rows)<5 or rows[-1]['time']-rows[0]['time']<.25:
            return 0.
        # Motion must also exist after camera compensation, not only in image coordinates.
        if sum(abs(r['measured']) for r in rows) < height*.006:
            return 0.
        sampled = [rows[0]]
        for row in rows[1:]:
            if row['time']-sampled[-1]['time'] >= .09:
                sampled.append(row)
        if len(sampled)<4:
            return 0.
        bar = np.diff([r['bar'] for r in sampled])
        person = np.diff([r['anchor'] for r in sampled])
        if np.ptp([r['bar'] for r in sampled])<height*.006:
            return 0.
        norm = np.linalg.norm(bar)*np.linalg.norm(person)
        agreement = float(np.dot(bar,person)/norm) if norm>0 else 0.
        error = np.linalg.norm(bar-person)/max(height*.002,np.linalg.norm(bar))
        return agreement-.25*error if agreement>=.75 and error<=.65 else 0.

    def complete_gaps(self, frames, height):
        """Bridge ownership only on an observed bar, with the same person still nearby.

        No shaft positions or motion are synthesized. Different confirmed owners bound
        separate intervals, so a spotter cannot inherit the lifter's measurement.
        """
        tracks = {}
        proposals = {}
        for frame in frames:
            for shaft in frame['shafts']:
                tracks.setdefault(shaft['trackId'],[]).append((frame,shaft))
        for rows in tracks.values():
            anchors = [i for i,(_,s) in enumerate(rows) if s['athleteId'] is not None]
            if not anchors:continue
            # Offline confirmation can recover preparation/first lift on the SAME
            # continuously observed bar. Stop at a missing person, ambiguity or gap.
            prefix=set();first=anchors[0];first_owner=rows[first][1]['athleteId']
            for j in range(first-1,-1,-1):
                f,s=rows[j]
                p=next((p for p in f['athletes'] if p['athleteId']==first_owner and p['trackingState']=='Tracked'),None)
                if rows[j+1][0]['timestampSeconds']-f['timestampSeconds']>.15 or s.get('ownershipAmbiguous',False) or p is None or not self._near_body(s,p,height):break
                prefix.add(j)
            cursor=0
            for i,(frame,shaft) in enumerate(rows):
                if shaft['athleteId'] is not None:continue
                if shaft.get('ownershipAmbiguous',False):continue
                while cursor<len(anchors) and anchors[cursor]<i:cursor+=1
                before=rows[anchors[cursor-1]] if cursor else None
                after=rows[anchors[cursor]] if cursor<len(anchors) else None
                owner=None;time=frame['timestampSeconds']
                if before and after and before[1]['athleteId']!=after[1]['athleteId']:continue
                if before and after and before[1]['athleteId']==after[1]['athleteId'] and after[0]['timestampSeconds']-before[0]['timestampSeconds']<=3:
                    owner=before[1]['athleteId']
                elif before and time-before[0]['timestampSeconds']<=.6:
                    owner=before[1]['athleteId']
                elif after and (i in prefix or after[0]['timestampSeconds']-time<=1.5):
                    owner=after[1]['athleteId']
                if owner is None or any(s is not shaft and s['athleteId']==owner for s in frame['shafts']):continue
                pose=next((p for p in frame['athletes'] if p['athleteId']==owner and p['trackingState']=='Tracked'),None)
                nearby=pose is not None and self._near_body(shaft,pose,height)
                if pose is None and before and after and before[1]['athleteId']==after[1]['athleteId'] and \
                    after[0]['timestampSeconds']-before[0]['timestampSeconds']<=2:
                    # Recovered identity bounds a brief pose outage. The same bar
                    # must remain observed throughout; only ownership is restored.
                    start,end=anchors[cursor-1],anchors[cursor]
                    continuous=all(not rows[j][1].get('ownershipAmbiguous',False) and
                        rows[j][0]['timestampSeconds']-rows[j-1][0]['timestampSeconds']<=.15
                        for j in range(start+1,end+1))
                    bounds=[next((p for p in f['athletes'] if p['athleteId']==owner and p['trackingState']=='Tracked'),None)
                            for f,_ in (before,after)]
                    nearby=continuous and all(p is not None and self._near_body(shaft,p,height) for p in bounds)
                if nearby:
                    proposals.setdefault((id(frame),owner),[]).append(shaft)
        for (_,owner),shafts in proposals.items():
            if len(shafts)==1:shafts[0]['athleteId']=owner
