"""Recompute association from saved multi-bar observations, without model inference."""
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ai'))
from motiontrace_ai.shaft_ownership import ShaftOwnership

source=Path(sys.argv[1]);target=Path(sys.argv[2]);target.mkdir(parents=True,exist_ok=True)
for path in source.glob('*.json'):
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('frames'),list) or not data['frames']:continue
    if 'shafts' not in data['frames'][0]:continue
    tracker=ShaftOwnership();height=data['video']['height']
    for frame in data['frames']:
        for shaft in frame['shafts']:shaft['athleteId']=None
        tracker.update(frame['timestampSeconds'],frame['shafts'],frame['athletes'],height)
    tracker.complete_gaps(data['frames'],height)
    for athlete in data['athletes']:athlete['isExerciseParticipant']=athlete['id'] in tracker.participants
    (target/path.name).write_text(json.dumps(data,separators=(',',':')))
    from collections import Counter
    print(path.name,'participants',tracker.participants,'owners',Counter(s['athleteId'] for f in data['frames'] for s in f['shafts']))
