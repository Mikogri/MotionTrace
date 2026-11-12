"""Validate and import the localization-only 300-frame review without altering its source."""
import collections,hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent

def validate(export,manifest):
 if export.get('schema')!=1 or export.get('dataset_id')!=manifest['dataset_id']:raise ValueError('Wrong dataset')
 base={t['id']:t for t in manifest['tasks']}
 if len(export['tasks'])!=len(base) or len({t['id'] for t in export['tasks']})!=len(base):raise ValueError('Missing or duplicate records')
 result=[]
 for task in export['tasks']:
  source=base[task['id']]
  for field in ['video_id','frame_index','timestamp','width','height']:
   if task[field]!=source[field]:raise ValueError(f'Changed source field {field}')
  status=task['review_status'];visibility=task['shaft_visibility'];segments=task['shaft_segments']
  if status not in ['unreviewed','draft','edited','approved'] or visibility not in ['unknown','visible','partial','occluded','absent']:raise ValueError('Invalid status')
  if not isinstance(segments,list):raise ValueError('Invalid segments')
  for s in segments:
   if len(s)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 or v>(source['height'] if i%2 else source['width']) for i,v in enumerate(s)):raise ValueError('Invalid coordinates')
  if status=='approved' and (visibility=='unknown' or (visibility in ['visible','partial'] and not segments) or (visibility in ['occluded','absent'] and segments)):raise ValueError('Approval contradicts visibility')
  row=dict(source);row.update(shaft_segments=segments,shaft_visibility=visibility,review_status=status,notes=str(task.get('notes','')),annotation_author='user_review')
  result.append(row)
 return result

def run():
 source=Path(sys.argv[1]) if len(sys.argv)>1 else HERE/'motiontrace-shaft-training-300.json'
 raw=source.read_bytes();export=json.loads(raw.decode('utf-8-sig'))
 manifest=json.loads((ROOT/'artifacts/barbell_training/manifest.json').read_text(encoding='utf-8'))
 tasks=validate(export,manifest)
 result=dict(schema=1,dataset_id=manifest['dataset_id'],annotation_target=manifest['annotation_target'],export_sha256=hashlib.sha256(raw).hexdigest(),videos=manifest['videos'],tasks=tasks)
 (HERE/'training_annotations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(statuses=dict(collections.Counter(t['review_status'] for t in tasks)),approved_visibility=dict(collections.Counter(t['shaft_visibility'] for t in tasks if t['review_status']=='approved'))),indent=2))
if __name__=='__main__':run()
