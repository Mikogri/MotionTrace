"""Visible shaft segmentation. ImageNet initialization is used only during training."""
import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torchvision.models import resnet18, ResNet18_Weights

SIZE = 512

def letterbox(image, size=SIZE):
    h, w = image.shape[:2]
    scale = size / max(h, w)
    nw, nh = round(w * scale), round(h * scale)
    x, y = (size - nw) // 2, (size - nh) // 2
    out = np.zeros((size, size, 3), np.uint8)
    out[y:y+nh, x:x+nw] = cv2.resize(image, (nw, nh))
    return out, (nw/w, nh/h, x, y)

def tensor(image):
    rgb = image[:, :, ::-1].copy().astype(np.float32) / 255
    rgb = (rgb - np.array([.485,.456,.406],np.float32)) / np.array([.229,.224,.225],np.float32)
    return torch.from_numpy(rgb.transpose(2,0,1))

def block(a,b):
    return nn.Sequential(nn.Conv2d(a,b,3,padding=1),nn.GroupNorm(8,b),nn.ReLU(),
                         nn.Conv2d(b,b,3,padding=1),nn.GroupNorm(8,b),nn.ReLU())

class ShaftNet(nn.Module):
    def __init__(self, pretrained=False):
        super().__init__()
        r=resnet18(weights=ResNet18_Weights.DEFAULT if pretrained else None)
        self.stem=nn.Sequential(r.conv1,r.bn1,r.relu)
        self.pool=r.maxpool
        self.layers=nn.ModuleList([r.layer1,r.layer2,r.layer3,r.layer4])
        self.decode=nn.ModuleList([block(512+256,128),block(128+128,64),block(64+64,32),block(32+64,32)])
        self.head=nn.Conv2d(32,1,1)

    def forward(self,x):
        shape=x.shape[-2:]; skips=[self.stem(x)]; x=self.pool(skips[0])
        for layer in self.layers:
            x=layer(x);skips.append(x)
        for layer,skip in zip(self.decode,reversed(skips[:-1])):
            x=layer(torch.cat([F.interpolate(x,size=skip.shape[-2:],mode='bilinear',align_corners=False),skip],1))
        return F.interpolate(self.head(x),size=shape,mode='bilinear',align_corners=False)

class ShaftDetector:
    def __init__(self, path, device='cpu'):
        self.device=device
        checkpoint=torch.load(path,map_location='cpu',weights_only=False)
        if checkpoint.get('architecture')!='shaft-resnet18-v1':raise ValueError('Unsupported shaft model')
        self.model=ShaftNet().to(device).eval();self.model.load_state_dict(checkpoint['state_dict'])
        self.threshold=checkpoint.get('threshold',.5)

    @torch.inference_mode()
    def probability(self,image):
        padded,transform=letterbox(image)
        return self.model(tensor(padded)[None].to(self.device)).sigmoid()[0,0].cpu().numpy(),transform

    def detect(self,image):
        probability,(sx,sy,ox,oy)=self.probability(image)
        mask=(probability>=self.threshold).astype(np.uint8)
        n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
        segments=[]
        for i in range(1,n):
            if stats[i,cv2.CC_STAT_AREA]<10:continue
            yy,xx=np.where(labels==i); points=np.column_stack([xx,yy]).astype(np.float32)
            vx,vy,x,y=cv2.fitLine(points,cv2.DIST_L2,0,.01,.01).reshape(-1)
            projection=(xx-x)*vx+(yy-y)*vy
            a,b=np.percentile(projection,[2,98])
            residual=np.abs((xx-x)*vy-(yy-y)*vx)
            if b-a<8 or np.percentile(residual,90)>max(6,(b-a)*.15):continue
            h,w=image.shape[:2]
            endpoints=[float(np.clip((x+a*vx-ox)/sx,0,w)),float(np.clip((y+a*vy-oy)/sy,0,h)),
                       float(np.clip((x+b*vx-ox)/sx,0,w)),float(np.clip((y+b*vy-oy)/sy,0,h))]
            segments.append(dict(line=endpoints,confidence=float(probability[yy,xx].mean())))
        return segments
