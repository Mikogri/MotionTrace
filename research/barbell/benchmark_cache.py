"""Measure full and pose-only cache reuse after benchmark_analysis.py completes."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

root=Path(__file__).resolve().parents[2]
base=root/'artifacts/analysis-performance'
out=base/'cache-reuse'
out.mkdir(exist_ok=False)
video=root/'videos/bench/100kg x 5.mp4'
expected=json.loads((base/'before/0c1164c17f6b.json').read_text())
shutil.copytree(base/'final/cache/poses',out/'pose-only/poses')
results=[]
for name,engine,cache in (
    ('baseline-full',base/'baseline/analyze.py',base/'before/cache'),
    ('optimized-full',root/'ai/analyze.py',base/'final/cache'),
    ('optimized-pose',root/'ai/analyze.py',out/'pose-only'),
):
    started=time.perf_counter()
    with (out/(name+'.log')).open('w') as log:
        subprocess.run([sys.executable,str(engine),'--input',str(video),
                        '--output',str(out/(name+'.json')),'--cache',str(cache),
                        '--device','cuda:0','--profile-output',str(out/(name+'.profile.json'))],
                       cwd=root,stdout=log,stderr=log,check=True)
    elapsed=time.perf_counter()-started
    actual=json.loads((out/(name+'.json')).read_text())
    equal=all(expected[key]==actual[key] for key in ('frames','athletes','video'))
    assert equal,name+' changed analysis results'
    results.append(dict(mode=name,wallSeconds=elapsed,exactResults=equal))
    (out/'timings.json').write_text(json.dumps(results,indent=2))
    print(results[-1],flush=True)
