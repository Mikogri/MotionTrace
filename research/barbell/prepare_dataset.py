"""Read-only video audit; no generated detection is a training label."""
import argparse, hashlib, json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]

def prepare(source, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'frames').mkdir(exist_ok=True)
    (output / 'baseline').mkdir(exist_ok=True)
    videos, tasks = [], []
    fractions = [.01, .08, .2, .35, .5, .65, .8, .95]
    for path in sorted(source.iterdir()):
        if path.suffix.lower() not in ('.mp4', '.mov', '.avi'): continue
        relative = path.relative_to(ROOT).as_posix()
        vid = hashlib.sha256(relative.encode()).hexdigest()[:12]
        cap = cv2.VideoCapture(str(path))
        cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        fps, count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not cap.isOpened() or fps <= 0: raise RuntimeError(f'Cannot open {path}')
        video = dict(id=vid, path=relative, name=path.name, bytes=path.stat().st_size,
                     mtime_ns=path.stat().st_mtime_ns, fps=fps, frame_count=count,
                     duration_estimate=count/fps, rotation=cap.get(cv2.CAP_PROP_ORIENTATION_META),
                     session_group=None, split='unassigned', frames=[])
        for index, fraction in enumerate(fractions):
            frame_index = min(count-1, round((count-1)*fraction))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = cap.read()
            if not ok: raise RuntimeError(f'Cannot decode {path} frame {frame_index}')
            timestamp = cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            height, width = frame.shape[:2]
            video.update(width=width, height=height)
            scale = min(1, 1280/max(width,height))
            frame = cv2.resize(frame, (round(width*scale), round(height*scale)))
            fid = f'{vid}_{frame_index:06d}'
            target = f'frames/{fid}.jpg'
            cv2.imwrite(str(output/target), frame, [cv2.IMWRITE_JPEG_QUALITY, 94])
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 60, 140)
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, 45,
                minLineLength=max(25, frame.shape[1]*.10), maxLineGap=12)
            candidates=[]
            if lines is not None:
                for x1,y1,x2,y2 in lines[:,0]:
                    if abs(y2-y1) > abs(x2-x1)*.7: continue
                    candidates.append([int(x1),int(y1),int(x2),int(y2)])
                candidates.sort(key=lambda l: -((l[2]-l[0])**2+(l[3]-l[1])**2))
            overlay=frame.copy()
            for line in candidates[:12]: cv2.line(overlay,tuple(line[:2]),tuple(line[2:]),(0,140,255),2)
            cv2.imwrite(str(output/f'baseline/{fid}.jpg'),overlay)
            task=dict(id=fid,video_id=vid,video_name=path.name,image=target,
                frame_index=frame_index,timestamp=timestamp,requested_frame=frame_index,
                width=frame.shape[1],height=frame.shape[0],original_width=width,original_height=height,
                baseline_candidates=candidates[:12],review_status='unreviewed',
                shaft_segments=[],athlete_box=None,bar_state='unknown',event='unknown',notes='')
            tasks.append(task); video['frames'].append(fid)
        cap.release();videos.append(video)
        print(f'{len(videos):02} {path.name}: {width}x{height}, {count/fps:.1f}s',flush=True)
    manifest=dict(schema=1,source=str(source),videos=videos,tasks=tasks,
        annotation_coordinates='oriented resized image pixels',
        warning='Hough candidates are unverified diagnostics, never ground truth. No train/test split until session grouping.')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    (output/'dataset.js').write_text('window.DATASET = '+json.dumps(manifest,ensure_ascii=False)+';',encoding='utf-8')
    for start in range(0,len(videos),5):
        sheet=Image.new('RGB',(1280,1200),'#171717');draw=ImageDraw.Draw(sheet)
        for row,video in enumerate(videos[start:start+5]):
            draw.text((8,row*240+5),f'{video["name"]} | {video["duration_estimate"]:.1f}s | {video["width"]}x{video["height"]}',fill='white')
            for col,index in enumerate([0,2,4,7]):
                task=next(t for t in tasks if t['id']==video['frames'][index])
                img=Image.open(output/task['image']);img.thumbnail((310,202))
                sheet.paste(img,(col*320+(320-img.width)//2,row*240+23))
                draw.text((col*320+8,row*240+224),f'{task["timestamp"]:.2f}s',fill='white')
        sheet.save(output/f'overview_{start//5+1}.jpg',quality=92)
    print(f'Prepared {len(videos)} videos, {len(tasks)} review frames; {sum(v["duration_estimate"] for v in videos):.1f}s',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=ROOT/'videos/bench')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/barbell_dataset')
    args=parser.parse_args();prepare(args.source,args.output)
