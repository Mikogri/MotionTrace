"""Prepare six local browser-compatible videos with source PTS for phase labeling."""
from pathlib import Path
from fractions import Fraction
import sys,json,hashlib
import av,cv2
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'ai'))
from motiontrace_ai.video_decode import VideoDecoder
out=root/'artifacts/phase-review-v1'
if out.exists():raise RuntimeError('Batch exists; do not overwrite user annotations.')
(out/'videos').mkdir(parents=True)
items=[]
for exercise in ('bench','squat','deadlift'):
 files=sorted(p for p in (root/'videos'/exercise).iterdir() if p.suffix.lower() in ('.mov','.mp4','.avi'))
 for path in (files[0],files[-1]):
  identity=hashlib.sha256(str(path.relative_to(root)).encode()).hexdigest()[:12]
  decoder=VideoDecoder(path);times=[]
  try:
   with av.open(str(out/'videos'/f'{identity}.mp4'),'w') as target:
    stream=target.add_stream('libx264',rate=Fraction(decoder.fps).limit_denominator(100000));scale=min(1,720/max(decoder.width,decoder.height))
    stream.width=round(decoder.width*scale/2)*2;stream.height=round(decoder.height*scale/2)*2;stream.pix_fmt='yuv420p';stream.time_base=Fraction(1,90000);stream.codec_context.time_base=stream.time_base;stream.options={'crf':'23','preset':'ultrafast','g':'30'}
    for time,image in decoder:
     times.append(time);image=cv2.resize(image,(stream.width,stream.height));frame=av.VideoFrame.from_ndarray(image,format='bgr24');frame.pts=round(time*90000);frame.time_base=Fraction(1,90000)
     for packet in stream.encode(frame):target.mux(packet)
    for packet in stream.encode():target.mux(packet)
   items.append(dict(id=identity,name=path.name,exercise=exercise,source=path.relative_to(root).as_posix(),video=f'videos/{identity}.mp4',timestamps=times))
   print(exercise,path.name,len(times),flush=True)
  finally:decoder.close()
data=dict(schema=1,dataset_id='motiontrace-phase-review-v1',videos=items)
(out/'dataset.js').write_text('window.DATASET='+json.dumps(data,ensure_ascii=False)+';',encoding='utf-8')
for name in ('review.html','review.js'):(out/name).write_text((root/'research/barbell/phase_review'/name).read_text(encoding='utf-8'),encoding='utf-8')
print(out)
