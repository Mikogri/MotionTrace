"""Prepare 300 temporally distributed, diversity-ranked shaft-localization frames."""
import hashlib,json,shutil
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/barbell_training'

def signature(frame):
 gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
 h,w=gray.shape
 return cv2.resize(gray[round(h*.3):round(h*.85)],(32,32)).astype(np.float32)

def run():
 base=json.loads((ROOT/'artifacts/barbell_dataset/manifest.json').read_text(encoding='utf-8'))
 videos=[dict(v) for v in base['videos'] if v['name']!='IMG_E0821.MOV']
 extra={v['id'] for v in sorted(videos,key=lambda v:-v['duration_estimate'])[:12]}
 old={v['id']:{t['frame_index'] for t in base['tasks'] if t['video_id']==v['id']} for v in videos}
 OUT.mkdir(exist_ok=True);(OUT/'frames').mkdir(exist_ok=True)
 tasks=[]
 for vi,v in enumerate(videos):
  cap=cv2.VideoCapture(str(ROOT/v['path']));cap.set(cv2.CAP_PROP_ORIENTATION_AUTO,1)
  quota=13 if v['id'] in extra else 12;selected=[];signatures=[]
  for slot in range(quota):
   choices=[]
   for fraction in (.28,.72):
    idx=round((slot+fraction)/quota*(v['frame_count']-1))
    while idx in old[v['id']] and idx<v['frame_count']-1:idx+=1
    cap.set(cv2.CAP_PROP_POS_FRAMES,idx);ok,frame=cap.read()
    if not ok:continue
    timestamp=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
    h,w=frame.shape[:2];scale=min(1,1280/max(h,w));frame=cv2.resize(frame,(round(w*scale),round(h*scale)))
    sig=signature(frame);score=min((float(np.mean(np.abs(sig-s))) for s in signatures),default=0)
    choices.append((score,idx,timestamp,frame,sig,w,h))
   if not choices:raise RuntimeError(f'Decode failed: {v["name"]} bin {slot}')
   score,idx,timestamp,frame,sig,w,h=max(choices,key=lambda c:c[0]);signatures.append(sig)
   fid=f'{v["id"]}_{idx:06d}';image=f'frames/{fid}.jpg';cv2.imwrite(str(OUT/image),frame,[cv2.IMWRITE_JPEG_QUALITY,94])
   tasks.append(dict(id=fid,video_id=v['id'],video_name=v['name'],image=image,frame_index=idx,timestamp=timestamp,
    width=frame.shape[1],height=frame.shape[0],original_width=w,original_height=h,
    shaft_segments=[],athlete_box=None,bar_state='unknown',event='unknown',shaft_visibility='unknown',notes='',review_status='unreviewed',
    selection_bin=slot,diversity_score=round(score,3)))
   selected.append(fid)
  cap.release();v['frames']=selected;v['split']='unassigned'
  print(f'{vi+1}/24 {v["name"]}: {quota} frames',flush=True)
 assert len(tasks)==300 and len({t['id'] for t in tasks})==300
 # Keep source frames and annotations intact; this is a separate batch and storage namespace.
 manifest=dict(schema=1,dataset_id='shaft-training-v1',annotation_target='visible_grip_shaft_segments',
  annotation_coordinates='oriented resized image pixels',videos=videos,tasks=tasks,
  excluded_videos=[{'name':'IMG_E0821.MOV','reason':'User identified a different exercise; excluded from this bench batch.'}],
  sampling='12 per video; 13 for 12 longest. Two candidates per temporal bin, choose largest minimum grayscale distance in middle/lower image. Heuristic, not guaranteed deduplication.')
 (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'dataset.js').write_text('window.DATASET = '+json.dumps(manifest,ensure_ascii=False)+';',encoding='utf-8')
 for name in ['review.html','review.js']:shutil.copyfile(ROOT/'research/barbell/training_review'/name,OUT/name)
 print('Ready: 300 frames, 24 source videos. No previous annotations overwritten.',flush=True)
if __name__=='__main__':run()
