import json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2];out=root/'artifacts/phase-engine-baseline'
import time
deadline=time.monotonic()+600
while not (root/'artifacts/shaft_multiexercise_v2_run2/evaluation.json').exists():
 if time.monotonic()>deadline:raise TimeoutError('Training did not complete; engine analysis was not started')
 time.sleep(2)
for r in json.loads((root/'research/barbell/phase_annotations.json').read_text(encoding='utf-8'))['records']:
 target=out/(r['video_id']+'.json')
 if target.exists():continue
 print('START '+r['source'],flush=True)
 subprocess.run([sys.executable,str(root/'ai/analyze.py'),'--input',str(root/r['source']),'--output',str(target),'--cache',str(out/'cache'),'--device','cuda:0'],stdout=(out/(r['video_id']+'.progress.log')).open('w'),stderr=(out/(r['video_id']+'.stderr.log')).open('w'),check=True)
 print('DONE '+r['source'],flush=True)
