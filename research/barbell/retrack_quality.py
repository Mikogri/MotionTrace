"""Compare tracker changes with cached poses; never overwrite previous experiments."""
import argparse,json,sys,time
from pathlib import Path
import torch

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'ai'))
from motiontrace_ai.shaft_model import ShaftDetector
from motiontrace_ai.shaft_tracking import ShaftTracker
from motiontrace_ai.video_decode import VideoDecoder

parser=argparse.ArgumentParser()
parser.add_argument('--model',default='ai/models/shaft-v1.pt')
parser.add_argument('--output',required=True)
args=parser.parse_args()
out=root/args.output
out.mkdir(exist_ok=False,parents=True)
torch.set_num_threads(4)
detector=ShaftDetector(root/args.model,'cuda:0')
timings=[]
for record in json.loads((root/'research/barbell/phase_annotations.json').read_text(encoding='utf-8'))['records']:
    start=time.monotonic()
    result=json.loads((root/'artifacts/phase-engine-baseline'/(record['video_id']+'.json')).read_text(encoding='utf-8-sig'))
    tracker=ShaftTracker(detector)
    decoder=VideoDecoder(root/record['source'])
    count=0
    try:
        for i,(timestamp,image) in enumerate(decoder):
            frame=result['frames'][i]
            assert abs(frame['timestampSeconds']-timestamp)<1e-5
            frame['shaft']=tracker.update(image,timestamp,frame['athletes'])
            count+=1
        assert count==len(result['frames'])
    finally:
        decoder.close()
    result['versions']['barbellModelVersion']=args.model+':'+ShaftTracker.VERSION
    (out/(record['video_id']+'.json')).write_text(json.dumps(result),encoding='utf-8')
    timings.append(dict(video=record['source'],frames=count,seconds=time.monotonic()-start))
    (out/'timings.json').write_text(json.dumps(timings,indent=2))
    print(timings[-1],flush=True)
