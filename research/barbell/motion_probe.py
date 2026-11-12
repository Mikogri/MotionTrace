"""Oracle-localized motion experiment. Uses user shaft labels, NOT an automatic detector."""
import json,csv
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def gray_at(cap,time,size):
 cap.set(cv2.CAP_PROP_POS_MSEC,max(0,time)*1000);ok,frame=cap.read()
 if not ok:return None
 return cv2.cvtColor(cv2.resize(frame,size),cv2.COLOR_BGR2GRAY)

def displacement(a,b,mask):
 points=cv2.goodFeaturesToTrack(a,maxCorners=100,qualityLevel=.01,minDistance=5,mask=mask,blockSize=5)
 if points is None or len(points)<3:return None,0
 kwargs=dict(winSize=(31,31),maxLevel=4,criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01))
 forward,status,_=cv2.calcOpticalFlowPyrLK(a,b,points,None,**kwargs)
 if forward is None:return None,0
 backward,backstatus,_=cv2.calcOpticalFlowPyrLK(b,a,forward,None,**kwargs)
 if backward is None:return None,0
 valid=(status[:,0]>0)&(backstatus[:,0]>0)&(np.linalg.norm(backward[:,0]-points[:,0],axis=1)<1.5)
 valid&=(forward[:,0,0]>=0)&(forward[:,0,0]<b.shape[1])&(forward[:,0,1]>=0)&(forward[:,0,1]<b.shape[0])
 delta=forward[:,0][valid]-points[:,0][valid]
 if len(delta)<3:return None,len(delta)
 # Reject inconsistent displacement within the small shaft support region.
 med=np.median(delta,axis=0);dist=np.linalg.norm(delta-med,axis=1)
 delta=delta[dist<=max(2,3*np.median(dist))]
 return (np.median(delta,axis=0) if len(delta)>=3 else None),len(delta)

def run():
 records=json.loads((HERE/'reviewed_annotations.json').read_text(encoding='utf-8'))
 manifest=json.loads((ROOT/'artifacts/barbell_dataset/manifest.json').read_text(encoding='utf-8'))
 videos={v['id']:v for v in manifest['videos']};results=[]
 for t in records:
  if t['review_status']!='approved' or t['geometry_review_required'] or t['bench_scope']!='candidate' or t['bar_state'] not in ('visible_moving','visible_stationary'):continue
  cap=cv2.VideoCapture(str(ROOT/videos[t['video_id']]['path']));cap.set(cv2.CAP_PROP_ORIENTATION_AUTO,1)
  size=(t['width'],t['height']);center=gray_at(cap,t['timestamp'],size)
  mask=np.zeros(center.shape,np.uint8)
  for s in t['shaft_segments']:cv2.line(mask,tuple(s[:2]),tuple(s[2:]),255,9)
  background=np.zeros(center.shape,np.uint8);background[:round(size[1]*.35),:]=255
  shifts=[0.];support=[]
  for dt in [-.4,-.2,.2,.4]:
   frame=gray_at(cap,t['timestamp']+dt,size)
   if frame is None:continue
   shift,n=displacement(center,frame,mask);camera,bn=displacement(center,frame,background)
   if shift is None or camera is None:continue
   shifts.append(float(shift[1]-camera[1]));support.append(n)
  cap.release()
  span=max(s[2] for s in t['shaft_segments'])-min(s[0] for s in t['shaft_segments'])
  threshold=max(3,span*.025)
  travel=max(shifts)-min(shifts)
  prediction='unknown' if len(support)<3 else 'visible_moving' if travel>threshold else 'visible_stationary'
  result=dict(id=t['id'],video=t['video_name'],timestamp=t['timestamp'],label=t['bar_state'],prediction=prediction,
   vertical_range_px=round(travel,3),threshold_px=round(threshold,3),supported_offsets=len(support),minimum_features=min(support) if support else 0,
   localization='user_annotation_oracle',window_seconds=.8)
  results.append(result);print(result,flush=True)
 (HERE/'motion_probe_results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
 with (HERE/'motion_probe_results.csv').open('w',newline='',encoding='utf-8') as f:
  writer=csv.DictWriter(f,fieldnames=results[0].keys());writer.writeheader();writer.writerows(results)
 print(f'{len(results)} labeled windows. Unknown is abstention. Not an independent detector accuracy estimate.',flush=True)
if __name__=='__main__':run()
