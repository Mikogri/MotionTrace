"""Small development check on previously labeled moving/stationary windows.
No manual shaft coordinates are supplied to the detector or tracker.
"""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai'))
import cv2,numpy as np,torch
from motiontrace_ai.shaft_model import ShaftDetector
from motiontrace_ai.shaft_tracking import ShaftTracker

torch.set_num_threads(4)
detector=ShaftDetector(ROOT/'ai/models/shaft-v1.pt','cuda:0')
records=json.loads((ROOT/'research/barbell/reviewed_annotations.json').read_text(encoding='utf-8'))
manifest=json.loads((ROOT/'artifacts/barbell_dataset/manifest.json').read_text(encoding='utf-8'))
videos={v['id']:v for v in manifest['videos']};results=[]
for t in records:
    if t['review_status']!='approved' or t['geometry_review_required'] or t['bench_scope']!='candidate' or t['bar_state'] not in ('visible_moving','visible_stationary'):continue
    cap=cv2.VideoCapture(str(ROOT/videos[t['video_id']]['path']));cap.set(cv2.CAP_PROP_ORIENTATION_AUTO,1)
    start=max(0,t['timestamp']-.4);cap.set(cv2.CAP_PROP_POS_MSEC,start*1000)
    tracker=ShaftTracker(detector);last=-1;total=0;positions=[0];support=0;decoded=0;track=None
    while True:
        ok,im=cap.read()
        if not ok:break
        time=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
        if time>t['timestamp']+.4:break
        if time-last<.03:continue
        last=time;h,w=im.shape[:2];im=cv2.resize(im,(round(w*640/h),640));s=tracker.update(im,time,[]);decoded+=1
        if s and s['motionReliable'] and (track is None or track==s['trackId']):
            total+=s['deltaY'];positions.append(total);support+=1
        elif track is not None:break
        if s:track=s['trackId']
    cap.release();travel=max(positions)-min(positions)
    prediction='unknown' if support<max(5,decoded*.6) else 'visible_moving' if travel>640*.004 else 'visible_stationary'
    row=dict(id=t['id'],video=t['video_name'],label=t['bar_state'],prediction=prediction,travel_px=travel,supported=support,decoded=decoded)
    results.append(row);print(json.dumps(row),flush=True)
(ROOT/'artifacts/shaft_model/motion-development.json').write_text(json.dumps({'rows':results,'limitations':'Nine development windows, same source corpus; not independent accuracy. Short-window labels may differ from the original two-second review context. No pose boxes supplied for background masking; no ownership or rep-count evaluation.'},indent=2))
