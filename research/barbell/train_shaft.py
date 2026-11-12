"""Train visible-fragment masks; splits are by provisional visual family, never frame."""
import argparse,copy,hashlib,json,random,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai'))
import cv2,numpy as np,torch
from torch.nn import functional as F
from motiontrace_ai.shaft_model import ShaftNet,letterbox,tensor,SIZE

def load_data():
    raw=(ROOT/'research/barbell/training_annotations.json').read_bytes()
    data=json.loads(raw);groups=json.loads((ROOT/'research/barbell/video_groups.json').read_text())
    splits={'train':[],'validation':[],'test':[]}
    for t in data['tasks']:
        group=groups[t['video_id']]
        split='test' if group=='low_window_20251014' else 'validation' if group=='front_ceiling_rack' else 'train'
        splits[split].append(t)
    return raw,splits

def sample(t):
    image=cv2.imread(str(ROOT/'artifacts/barbell_training'/t['image']))
    if image is None:raise ValueError(t['image'])
    image,(sx,sy,x,y)=letterbox(image);mask=np.zeros((SIZE,SIZE),np.uint8)
    for a,b,c,d in t['shaft_segments']:
        cv2.line(mask,(round(a*sx+x),round(b*sy+y)),(round(c*sx+x),round(d*sy+y)),1,3)
    return image,mask

def augment(image,mask):
    matrix=cv2.getRotationMatrix2D((SIZE/2,SIZE/2),random.uniform(-12,12),random.uniform(.85,1.1))
    matrix[:,2]+=np.random.uniform(-25,25,2)
    image=cv2.warpAffine(image,matrix,(SIZE,SIZE));mask=cv2.warpAffine(mask,matrix,(SIZE,SIZE),flags=cv2.INTER_NEAREST)
    if random.random()<.5:image=image[:,::-1].copy();mask=mask[:,::-1].copy()
    image=np.clip(image.astype(np.float32)*random.uniform(.65,1.35)+random.uniform(-15,15),0,255).astype(np.uint8)
    return image,mask

def run(args):
    random.seed(42);np.random.seed(42);torch.manual_seed(42);torch.set_num_threads(4)
    torch.backends.cudnn.benchmark=True
    raw,splits=load_data();out=ROOT/'artifacts/shaft_model';out.mkdir(exist_ok=True)
    (out/'split.json').write_text(json.dumps({k:[t['id'] for t in v] for k,v in splits.items()},indent=2))
    cache={t['id']:sample(t) for rows in splits.values() for t in rows}
    model=ShaftNet(pretrained=True).cuda();optimizer=torch.optim.AdamW(model.parameters(),lr=.0003,weight_decay=.0001)
    scaler=torch.cuda.amp.GradScaler();best=-1;history=[]
    for epoch in range(args.epochs):
        start=time.time();model.train();order=splits['train'].copy();random.shuffle(order);losses=[]
        for offset in range(0,len(order),args.batch):
            batch=[augment(*cache[t['id']]) for t in order[offset:offset+args.batch]]
            x=torch.stack([tensor(im) for im,m in batch]).cuda();y=torch.from_numpy(np.stack([m for im,m in batch])[:,None].astype(np.float32)).cuda()
            optimizer.zero_grad(set_to_none=True)
            with torch.cuda.amp.autocast():
                logits=model(x);prob=logits.sigmoid()
                bce=F.binary_cross_entropy_with_logits(logits,y,pos_weight=torch.tensor(12.,device='cuda'))
                dice=1-(2*(prob*y).sum((1,2,3))+1)/(prob.sum((1,2,3))+y.sum((1,2,3))+1)
                loss=bce+dice.mean()
            scaler.scale(loss).backward();scaler.step(optimizer);scaler.update();losses.append(loss.item())
        model.eval();tp=fp=fn=0
        with torch.inference_mode():
            for t in splits['validation']:
                im,mask=cache[t['id']];p=model(tensor(im)[None].cuda()).sigmoid()[0,0].cpu().numpy()>=.5;y=mask>0
                tp+=int((p&y).sum());fp+=int((p&~y).sum());fn+=int((~p&y).sum())
        f1=2*tp/max(1,2*tp+fp+fn)
        row=dict(epoch=epoch+1,loss=float(np.mean(losses)),validation_mask_f1=f1,seconds=round(time.time()-start,1));history.append(row);print(json.dumps(row),flush=True)
        if f1>best:
            best=f1;torch.save(dict(architecture='shaft-resnet18-v1',state_dict={k:v.cpu() for k,v in model.state_dict().items()},threshold=.5,epoch=epoch+1,annotation_sha256=hashlib.sha256(raw).hexdigest(),validation_mask_f1=f1),out/'best.pt')
        (out/'history.json').write_text(json.dumps(history,indent=2))
    print('Training complete',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--epochs',type=int,default=30);p.add_argument('--batch',type=int,default=6);run(p.parse_args())
