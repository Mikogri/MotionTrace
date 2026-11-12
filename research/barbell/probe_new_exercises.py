"""Reproducible sparse baseline, not an accuracy benchmark without labels."""
import sys,json
from pathlib import Path
import av,cv2,torch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ai'))
from motiontrace_ai.shaft_model import ShaftDetector
root=Path(__file__).resolve().parents[2];out=root/'artifacts/new-exercises-baseline';out.mkdir(exist_ok=True)
torch.set_num_threads(4);detector=ShaftDetector(root/'ai/models/shaft-v1.pt','cuda' if torch.cuda.is_available() else 'cpu')
rows=[]
for exercise in ('squat','deadlift'):
 thumbnails=[]
 for path in sorted((root/'videos'/exercise).iterdir()):
  if path.suffix.lower() not in ('.mov','.mp4','.avi'):continue
  with av.open(str(path)) as container:
   stream=container.streams.video[0];duration=float(stream.duration*stream.time_base)
   for fraction in (.25,.5,.75):
    target=duration*fraction;container.seek(int(target/float(stream.time_base)),stream=stream)
    frame=next(f for f in container.decode(stream) if f.time is not None and f.time>=target)
    image=frame.to_ndarray(format='bgr24')
    if frame.rotation==-90:image=cv2.rotate(image,cv2.ROTATE_90_CLOCKWISE)
    elif frame.rotation==90:image=cv2.rotate(image,cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif abs(frame.rotation)==180:image=cv2.rotate(image,cv2.ROTATE_180)
    segments=detector.detect(image)
    rows.append(dict(exercise=exercise,video=path.name,time=frame.time,duration=duration,segments=segments))
    for segment in segments:
     x1,y1,x2,y2=map(round,segment['line']);cv2.line(image,(x1,y1),(x2,y2),(0,255,255),4)
    scale=min(320/image.shape[1],250/image.shape[0]);image=cv2.resize(image,None,fx=scale,fy=scale)
    import numpy as np
    tile=np.full((285,340,3),30,np.uint8);tile[:image.shape[0],:image.shape[1]]=image
    cv2.putText(tile,f'{path.stem} {frame.time:.1f}s ({len(segments)})',(4,275),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1)
    thumbnails.append(tile)
 for batch in range(0,len(thumbnails),12):
  tiles=thumbnails[batch:batch+12];tiles += [np.zeros_like(tiles[0])]*(12-len(tiles))
  sheet=np.vstack([np.hstack(tiles[i:i+4]) for i in range(0,12,4)])
  cv2.imwrite(str(out/f'{exercise}-{batch//12+1}.jpg'),sheet)
 print(exercise, 'samples',sum(r['exercise']==exercise for r in rows),'with detections',sum(r['exercise']==exercise and bool(r['segments']) for r in rows),flush=True)
(out/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
