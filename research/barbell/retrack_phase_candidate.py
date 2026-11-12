"""Re-run only shaft detection/tracking using cached person poses on original frames."""
import json,sys,copy,time
from pathlib import Path
import torch
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'ai'))
from motiontrace_ai.shaft_model import ShaftDetector
from motiontrace_ai.shaft_tracking import ShaftTracker
from motiontrace_ai.video_decode import VideoDecoder
source=root/'artifacts/phase-engine-baseline';out=root/'artifacts/phase-engine-candidate';out.mkdir(exist_ok=True)
deadline=time.monotonic()+1200
records=json.loads((root/'research/barbell/phase_annotations.json').read_text(encoding='utf-8'))['records']
while not all((source/(r['video_id']+'.json')).exists() for r in records):
 if time.monotonic()>deadline:raise TimeoutError('Full baseline analyses missing')
 time.sleep(3)
torch.set_num_threads(4);detector=ShaftDetector(root/'artifacts/shaft_multiexercise_v2_run2/candidate.pt','cuda:0')
for record in json.loads((root/'research/barbell/phase_annotations.json').read_text(encoding='utf-8'))['records']:
 path=source/(record['video_id']+'.json');result=json.loads(path.read_text(encoding='utf-8-sig'));tracker=ShaftTracker(detector);decoder=VideoDecoder(root/record['source']);n=0
 try:
  for i,(timestamp,image) in enumerate(decoder):
   frame=result['frames'][i];assert abs(frame['timestampSeconds']-timestamp)<1e-5
   frame['shaft']=tracker.update(image,timestamp,frame['athletes']);n+=1
  assert n==len(result['frames'])
 finally:decoder.close()
 result['versions']['barbellModelVersion']='research-shaft-v2-candidate'
 (out/path.name).write_text(json.dumps(result),encoding='utf-8');print('RETRACKED '+record['source'],flush=True)
