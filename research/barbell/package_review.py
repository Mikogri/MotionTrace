"""Apply separately preserved visual drafts and package a portable, offline review page."""
import json, shutil
from pathlib import Path
import cv2
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/barbell_dataset'
SOURCE=Path(__file__).resolve().parent

def package():
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    seeds=json.loads((SOURCE/'seed_annotations.json').read_text(encoding='utf-8'))
    groups=json.loads((SOURCE/'video_groups.json').read_text(encoding='utf-8'))
    for video in manifest['videos']:
        video['visual_family_proposal']=groups.get(video['id'])
    lookup={t['id']:t for t in manifest['tasks']}
    reviewed=SOURCE/'reviewed_annotations.json'
    if reviewed.exists():
        for item in json.loads(reviewed.read_text(encoding='utf-8')):
            if item['id'] in lookup and lookup[item['id']]['review_status'] not in ('approved','edited'):
                lookup[item['id']].update(item)
    manifest['review_queue']=[t['id'] for t in seeds]
    (OUT/'context').mkdir(exist_ok=True)
    for seed in seeds:
        task=lookup[seed['id']]
        if task['review_status'] not in ('approved','edited'):
            for field in ('shaft_segments','athlete_box','event','notes','review_status','bar_state','annotation_author'):
                task[field]=seed[field]
        video=next(v for v in manifest['videos'] if v['id']==task['video_id'])
        output=OUT/'context'/f'{task["id"]}.webp'
        if not output.exists():
            cap=cv2.VideoCapture(str(ROOT/video['path']));cap.set(cv2.CAP_PROP_ORIENTATION_AUTO,1)
            frames=[];times=[]
            for offset in range(-10,11):
                time=max(0,min(video['duration_estimate']-.1,task['timestamp']+offset*.1))
                cap.set(cv2.CAP_PROP_POS_MSEC,time*1000);ok,bgr=cap.read()
                if not ok:continue
                h,w=bgr.shape[:2];bgr=cv2.resize(bgr,(round(w*640/max(w,h)),round(h*640/max(w,h))))
                frames.append(Image.fromarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)))
                times.append(cap.get(cv2.CAP_PROP_POS_MSEC)/1000)
            cap.release()
            if len(frames)<2:raise RuntimeError(f'Context decode failed: {task["id"]}')
            frames[0].save(output,save_all=True,append_images=frames[1:],duration=100,loop=0,quality=82)
            output.with_suffix('.json').write_text(json.dumps({'source_timestamps':times,'playback_frame_ms':100}),encoding='utf-8')
        task['context_image']=f'context/{output.name}'
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'dataset.js').write_text('window.DATASET = '+json.dumps(manifest,ensure_ascii=False)+';',encoding='utf-8')
    for name in ['review.html','review.js']:shutil.copyfile(SOURCE/name,OUT/name)
    print(f'Packaged {len(seeds)} examples with animated context; existing user reviews preserved.',flush=True)

if __name__=='__main__':package()
