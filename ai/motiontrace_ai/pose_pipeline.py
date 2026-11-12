"""Person detection, identity tracking and pose inference, independent of shaft processing."""
import contextlib
import sys
import time
import numpy as np
from mmdet.apis import inference_detector
from mmpose.apis import inference_topdown
from mmengine.registry import init_default_scope
from .mapping import map_instance
from .person_tracking import PersonTracker, StableCrop, appearance_descriptor
from .tracking import overlap


class PosePipeline:
    def __init__(self,inferencer,padding,selected,timings):
        self.inferencer=inferencer
        self.selected=selected
        self.timings=timings
        self.tracker=PersonTracker()
        self.crops=StableCrop(padding=padding)

    def update(self,image,timestamp,width,height):
        tracker,crops,selected,inferencer,timings=self.tracker,self.crops,self.selected,self.inferencer,self.timings
        detection_started=time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr):
            init_default_scope('mmdet')
            detected = inference_detector(inferencer.inferencer.detector.model, image).pred_instances.cpu().numpy()
        timings.seconds['personDetection']=timings.seconds.get('personDetection',0)+time.perf_counter()-detection_started
        tracking_started=time.perf_counter()
        detections = []
        for box, score, label in zip(detected.bboxes, detected.scores, detected.labels):
            if label != 0 or score < .2: continue
            if box[2] <= box[0] or box[3] <= box[1] or not np.isfinite(box).all(): continue
            detections.append(dict(box=box.tolist(), confidence=float(score), appearance=appearance_descriptor(image,box)))
        matched, lost = tracker.update(detections, timestamp)
        poses = []
        crop_by_id={track.identity:crops.update(track.identity,track.box,timestamp,width,height) for track,detection in matched}
        pose_tracks=[track for track,detection in matched if not selected or track.identity in selected]
        predicted_by_id={}
        timings.seconds['personTracking']=timings.seconds.get('personTracking',0)+time.perf_counter()-tracking_started
        pose_started=time.perf_counter()
        if pose_tracks:
            with contextlib.redirect_stdout(sys.stderr):
                # One GPU batch for all people, retaining every frame and the same pose model.
                predicted_batch=inference_topdown(inferencer.inferencer.model,image,
                    np.array([crop_by_id[t.identity] for t in pose_tracks],dtype=np.float32))
            predicted_by_id={t.identity:p.pred_instances for t,p in zip(pose_tracks,predicted_batch)}
        timings.seconds['pose']=timings.seconds.get('pose',0)+time.perf_counter()-pose_started
        mapping_started=time.perf_counter()
        for track, detection in matched:
            box = track.box
            crop = crop_by_id[track.identity]
            risk = max([overlap(box,d['box']) for t,d in matched if t.identity!=track.identity] or [0])
            risk_name = 'High' if risk>.45 else 'Medium' if risk>.15 else 'Low'
            keypoints=[]
            if not selected or track.identity in selected:
                predicted = predicted_by_id[track.identity]
                mapped = map_instance(dict(keypoints=predicted.keypoints[0].tolist(),keypoint_scores=predicted.keypoint_scores[0].tolist(),bbox=[box],bbox_score=1))
                keypoints = mapped['keypoints'] if mapped else []
            x1,y1,x2,y2=box
            poses.append(dict(athleteId=track.identity,boundingBox=dict(x=x1,y=y1,width=x2-x1,height=y2-y1),
                cropBox=dict(x=crop[0],y=crop[1],width=crop[2]-crop[0],height=crop[3]-crop[1]),
                confidence=detection['confidence'],trackingConfidence=track.confidence,trackingState='Tracked',occlusionRisk=risk_name,keypoints=keypoints))
        for track in lost:
            x1,y1,x2,y2=track.box
            poses.append(dict(athleteId=track.identity,boundingBox=dict(x=x1,y=y1,width=x2-x1,height=y2-y1),
                confidence=0,trackingConfidence=0,trackingState='Lost',occlusionRisk='High',keypoints=[]))
        timings.seconds['poseMapping']=timings.seconds.get('poseMapping',0)+time.perf_counter()-mapping_started
        return poses
