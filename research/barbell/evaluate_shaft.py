"""Report held-family mask and extracted-line coverage; save visual overlays."""
import json,sys
from pathlib import Path
import cv2,numpy as np,torch
from train_shaft import ROOT,load_data,sample
from motiontrace_ai.shaft_model import ShaftDetector,SIZE

def run():
    torch.set_num_threads(4)
    detector=ShaftDetector(ROOT/'artifacts/shaft_model/best.pt','cuda:0')
    _,splits=load_data();report={};tiles=[]
    for split in ['validation','test']:
        totals=np.zeros(6,np.int64);rows=[]
        for j,t in enumerate(splits[split]):
            image=cv2.imread(str(ROOT/'artifacts/barbell_training'/t['image']))
            probability,transform=detector.probability(image);p=probability>=detector.threshold
            _,target=sample(t);y=target>0
            tolerance=cv2.dilate(target,np.ones((7,7),np.uint8))>0
            predicted=cv2.dilate(p.astype(np.uint8),np.ones((7,7),np.uint8))>0
            counts=np.array([(p&y).sum(),p.sum(),y.sum(),(p&tolerance).sum(),(y&predicted).sum(),0])
            segments=detector.detect(image);counts[5]=len(segments)>0;totals+=counts
            rows.append(dict(id=t['id'],segments=len(segments),mask_pixels=int(p.sum())))
            if j%max(1,len(splits[split])//8)==0:
                for x1,y1,x2,y2 in t['shaft_segments']:cv2.line(image,(round(x1),round(y1)),(round(x2),round(y2)),(0,255,0),3)
                for s in segments:
                    x1,y1,x2,y2=map(round,s['line']);cv2.line(image,(x1,y1),(x2,y2),(255,0,255),2)
                thumb=cv2.resize(image,(225,400));cv2.putText(thumb,f'{split} {j+1}',(5,18),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,255,255),1);tiles.append(thumb)
        tp,pp,yy,near,covered,present=map(int,totals)
        report[split]=dict(frames=len(rows),mask_f1=2*tp/max(1,pp+yy),precision_with_3px_tolerance=near/max(1,pp),recall_with_3px_tolerance=covered/max(1,yy),frames_with_extracted_lines=present,rows=rows)
    report['limitations']='Development holdout by provisional visual family, not an independent final test. Pixel scores are not rep-count accuracy. Only one absent annotation overall; no meaningful absent-bar specificity estimate.'
    out=ROOT/'artifacts/shaft_model';(out/'evaluation.json').write_text(json.dumps(report,indent=2))
    while len(tiles)%4:tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(str(out/'evaluation.jpg'),np.vstack([np.hstack(tiles[i:i+4]) for i in range(0,len(tiles),4)]))
    print(json.dumps({k:{a:b for a,b in v.items() if a!='rows'} if isinstance(v,dict) else v for k,v in report.items()},indent=2))

if __name__=='__main__':run()
