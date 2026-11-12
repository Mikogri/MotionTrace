"""Verify exact analysis equivalence and summarize measured process wall times."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
base=root/'artifacts/analysis-performance'
before=json.loads((base/'before/timings.json').read_text())
rows=[]
for old in before:
    expected=json.loads((base/'before'/(old['id']+'.json')).read_text())
    row=dict(video=old['video'],frames=len(expected['frames']),beforeSeconds=old['wallSeconds'])
    for mode in ('after','after-sync','final'):
        timings=json.loads((base/mode/'timings.json').read_text())
        timing=next(t for t in timings if t['id']==old['id'])
        actual=json.loads((base/mode/(old['id']+'.json')).read_text())
        equal=all(expected[key]==actual[key] for key in ('frames','athletes','video'))
        assert equal,(mode,old['video'])
        row[mode]=dict(seconds=timing['wallSeconds'],exactResults=equal)
    rows.append(row)
(base/'comparison.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
