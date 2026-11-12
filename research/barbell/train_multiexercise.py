"""Fine-tune a separate shaft candidate; no production model replacement."""
import json,hashlib,random,time,sys
from pathlib import Path
import cv2,numpy as np,torch
from torch.nn import functional as F
from train_shaft import ROOT,load_data,sample,augment
from motiontrace_ai.shaft_model import ShaftNet,tensor
OUT=ROOT/'artifacts/shaft_multiexercise_v2_run2'
def data():
 raw,splits=load_data()
 for rows in splits.values():
  for t in rows:t['exercise']='bench'
 new=json.loads((ROOT/'research/barbell/squat_deadlift_annotations.json').read_text(encoding='utf-8'));videos={v['id']:v for v in new['videos']}
 for task in new['tasks']:
  assert task['review_status']=='approved'
  v=videos[task['video_id']];task=dict(task,exercise=v['exercise'],image=str(ROOT/'artifacts/shaft-squat-deadlift-review'/task['image']))
  # Hold out all non-IMG sources together; consecutive IMG sessions stay in training.
  split='validation' if not v['name'].startswith('IMG_') else 'train'
  splits[split].append(task)
 return splits

def evaluate(model,rows,cache):
 scores={}
 model.eval()
 with torch.inference_mode():
  for exercise in sorted({t['exercise'] for t in rows}):
   counts=np.zeros(5,dtype=np.int64)
   for t in rows:
    if t['exercise']!=exercise:continue
    im,mask=cache[t['id']];pred=model(tensor(im)[None].cuda()).sigmoid()[0,0].cpu().numpy()>=.5;y=mask>0
    near=cv2.dilate(mask,np.ones((7,7),np.uint8))>0;expanded=cv2.dilate(pred.astype(np.uint8),np.ones((7,7),np.uint8))>0
    counts+=np.array([(pred&y).sum(),pred.sum(),y.sum(),(pred&near).sum(),(y&expanded).sum()])
   tp,pp,yy,near,covered=map(int,counts);scores[exercise]=dict(mask_f1=2*tp/max(1,pp+yy),precision_3px=near/max(1,pp),recall_3px=covered/max(1,yy),frames=sum(t['exercise']==exercise for t in rows))
 return scores

def run():
 OUT.mkdir(exist_ok=False);random.seed(42);np.random.seed(42);torch.manual_seed(42);torch.set_num_threads(4)
 splits=data();assert not ({t['video_id'] for t in splits['train']} & {t['video_id'] for t in splits['validation']+splits['test']})
 manifest={k:[dict(id=t['id'],video_id=t['video_id'],exercise=t['exercise']) for t in rows] for k,rows in splits.items()}
 (OUT/'split.json').write_text(json.dumps(manifest,indent=2))
 hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['ai/models/shaft-v1.pt','research/barbell/training_annotations.json','research/barbell/squat_deadlift_annotations.json']};(OUT/'inputs.json').write_text(json.dumps(hashes,indent=2))
 cache={t['id']:sample(t) for rows in splits.values() for t in rows}
 model=ShaftNet().cuda();model.load_state_dict(torch.load(ROOT/'ai/models/shaft-v1.pt',map_location='cpu',weights_only=False)['state_dict'])
 baseline=evaluate(model,splits['validation'],cache);baseline_test=evaluate(model,splits['test'],cache)
 (OUT/'baseline.json').write_text(json.dumps(dict(validation=baseline,test=baseline_test),indent=2));print('BASELINE '+json.dumps(baseline),flush=True)
 optimizer=torch.optim.AdamW(model.parameters(),lr=.0001,weight_decay=.0001);scaler=torch.cuda.amp.GradScaler();best=-1;history=[]
 for epoch in range(12):
  start=time.time();model.train();order=splits['train'].copy();random.shuffle(order);losses=[]
  for offset in range(0,len(order),6):
   batch=[augment(*cache[t['id']]) for t in order[offset:offset+6]];x=torch.stack([tensor(im) for im,m in batch]).cuda();y=torch.from_numpy(np.stack([m for im,m in batch])[:,None].astype(np.float32)).cuda();optimizer.zero_grad(set_to_none=True)
   with torch.autocast('cuda'):
    logits=model(x);prob=logits.sigmoid();loss=F.binary_cross_entropy_with_logits(logits,y,pos_weight=torch.tensor(12.,device='cuda'))+(1-(2*(prob*y).sum((1,2,3))+1)/(prob.sum((1,2,3))+y.sum((1,2,3))+1)).mean()
   scaler.scale(loss).backward();scaler.step(optimizer);scaler.update();losses.append(loss.item())
  scores=evaluate(model,splits['validation'],cache);macro=np.mean([s['mask_f1'] for s in scores.values()]);row=dict(epoch=epoch+1,loss=float(np.mean(losses)),validation=scores,macro_f1=float(macro),seconds=time.time()-start);history.append(row);print(json.dumps(row),flush=True)
  if macro>best:
   best=macro;torch.save(dict(architecture='shaft-resnet18-v1',state_dict={k:v.cpu() for k,v in model.state_dict().items()},threshold=.5,epoch=epoch+1,validation=scores,input_hashes=hashes),OUT/'candidate.pt')
  (OUT/'history.json').write_text(json.dumps(history,indent=2))
 model.load_state_dict(torch.load(OUT/'candidate.pt',map_location='cpu',weights_only=False)['state_dict'])
 final=dict(validation=evaluate(model,splits['validation'],cache),test=evaluate(model,splits['test'],cache),limitations='Development validation with provisional source-family grouping. New exercises have no independent final test. Mask metrics are not phase or speed accuracy. Production model unchanged.')
 (OUT/'evaluation.json').write_text(json.dumps(final,indent=2));print('FINAL '+json.dumps(final),flush=True)
if __name__=='__main__':run()
