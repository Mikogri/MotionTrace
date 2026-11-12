"""Validate the user's export without modifying it; preserve provenance and flag geometry conflicts."""
import collections, hashlib, json, math, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'artifacts/barbell_dataset'

def overlaps(a,b):
    # Collinear overlapping strokes may be a replacement drawn without deleting a draft.
    dx,dy=a[2]-a[0],a[3]-a[1];length=math.hypot(dx,dy)
    if length<1:return True
    distances=[abs(dx*(b[i+1]-a[1])-dy*(b[i]-a[0]))/length for i in (0,2)]
    projected=[((b[i]-a[0])*dx+(b[i+1]-a[1])*dy)/length for i in (0,2)]
    overlap=max(0,min(length,max(projected))-max(0,min(projected)))
    return max(distances)<10 and overlap>min(length,math.hypot(b[2]-b[0],b[3]-b[1]))*.3

def run():
    source=Path(sys.argv[1]) if len(sys.argv)>1 else HERE/'motiontrace-shaft-review.json'
    raw=source.read_bytes();export=json.loads(raw.decode('utf-8-sig'))
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    lookup={t['id']:t for t in manifest['tasks']}
    assert export['schema']==1 and 0<len(export['tasks'])<=len(lookup)
    assert len({t['id'] for t in export['tasks']})==len(export['tasks'])
    accepted={t['id']:t for t in manifest['tasks'] if t['review_status'] in ('approved','edited')};issues=[]
    for t in export['tasks']:
        original=lookup[t['id']]
        assert Path(t['image']).name==Path(original['image']).name
        for field in ['video_id','width','height','frame_index','timestamp']:
            assert t[field]==original[field],(t['id'],field)
        assert t['review_status'] in ['unreviewed','draft','edited','approved']
        assert t['bar_state'] in ['unknown','visible_stationary','visible_moving','occluded','absent']
        assert t['event'] in ['unknown','setup_empty_hands','setup_contact','unrack','rep','rerack','spotter_assist','between_sets']
        for coords in t['shaft_segments']+([t['athlete_box']] if t.get('athlete_box') else []):
            assert len(coords)==4 and all(isinstance(x,(int,float)) and math.isfinite(x) and 0<=x<=(t['height'] if i%2 else t['width']) for i,x in enumerate(coords))
        if t['review_status'] not in ['approved','edited']:continue
        item=dict(original)
        for field in ['shaft_segments','athlete_box','bar_state','event','notes','review_status']:item[field]=t[field]
        item['annotation_author']='user_review'
        item['review_export_sha256']=hashlib.sha256(raw).hexdigest()
        item['geometry_review_required']=any(overlaps(a,b) for i,a in enumerate(t['shaft_segments']) for b in t['shaft_segments'][i+1:])
        item['bench_scope']='excluded_user_other_exercise' if t['video_name']=='IMG_E0821.MOV' and 'leg press' in t.get('notes','').lower() else 'candidate'
        item['training_ready']=False # Neither a session split nor a validated training set exists yet.
        if item['geometry_review_required']:issues.append({'id':t['id'],'reason':'Overlapping strokes: retain as user input; resolve before training.'})
        if '\ufffd' in item.get('notes',''):issues.append({'id':t['id'],'reason':'Export contains replacement characters in notes; original preserved.'})
        original.update(item);accepted[t['id']]=item
    accepted=list(accepted.values())
    report={'schema':1,'export_sha256':hashlib.sha256(raw).hexdigest(),
        'statuses':dict(collections.Counter(t['review_status'] for t in export['tasks'])),
        'approved_bar_states':dict(collections.Counter(t['bar_state'] for t in accepted if t['review_status']=='approved')),
        'geometry_conflicts':[t['id'] for t in accepted if t['geometry_review_required']],
        'other_exercise':[t['id'] for t in accepted if t['bench_scope']!='candidate'], 'issues':issues}
    (HERE/'reviewed_annotations.json').write_text(json.dumps(accepted,indent=2,ensure_ascii=False),encoding='utf-8')
    (HERE/'review_import_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    (OUT/'dataset.js').write_text('window.DATASET = '+json.dumps(manifest,ensure_ascii=False)+';',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':run()
