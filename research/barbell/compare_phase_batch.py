"""Match predicted phases by lift overlap, without using labels to detect reps."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
folder=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(exist_ok=True,parents=True)
labels=json.loads((ROOT/'research/barbell/phase_annotations.json').read_text(encoding='utf-8'));report=[]
for record in labels['records']:
 path=folder/(record['video_id']+'.json')
 if not path.exists():report.append(dict(video=record['source'],error='analysis missing'));continue
 exercise={'bench':'BenchPress','squat':'Squat','deadlift':'Deadlift'}[record['exercise']]
 call=subprocess.run(['dotnet','run','--project',str(ROOT/'research/barbell/AnalysisProbe'),'--',str(path),exercise],capture_output=True,text=True,encoding='utf-8',check=True)
 d=json.loads(call.stdout[call.stdout.index('{'):]);(out/(record['video_id']+'.json')).write_text(json.dumps(d,indent=2))
 pred=d['shaftReps'];used=set();matches=[]
 for i,r in enumerate(record['reps']):
  a,b=r['lifting_start']['time'],r['lifting_end']['time'];overlap=lambda p:max(0,min(b,p['liftingEnd'])-max(a,p['liftingStart']))/max(.001,max(b,p['liftingEnd'])-min(a,p['liftingStart']))
  candidates=[(overlap(p),j,p) for j,p in enumerate(pred) if j not in used];best=max(candidates,default=(0,None,None),key=lambda x:x[0])
  if best[0]<.2:matches.append(dict(rep=i+1,matched=False));continue
  _,j,p=best;used.add(j);errors={}
  for field,key in [('lowering_start','loweringStart'),('lowering_end','loweringEnd'),('lifting_start','liftingStart'),('lifting_end','liftingEnd')]:
   if field in r and p.get(key) is not None:errors[field]=p[key]-r[field]['time']
  matches.append(dict(rep=i+1,matched=True,errors_s=errors))
 report.append(dict(video=record['source'],expected=len(record['reps']),detected=len(pred),false_positive=len(pred)-len(used),matches=matches))
(out/'comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
