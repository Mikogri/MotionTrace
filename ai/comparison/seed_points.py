"""Use the local shaft model once to suggest TAPNext++ queries on frame zero."""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def choose_points(segments, width, height, image=None):
    candidates = []
    for segment in segments:
        line = segment['line']
        if len(line) != 4 or not all(math.isfinite(v) for v in line):
            continue
        x1, y1, x2, y2 = line
        length = math.hypot(x2-x1, y2-y1)
        if not math.isfinite(segment['confidence']) or segment['confidence'] < .5 or length < min(width, height)*.03:
            continue
        points = [dict(x=min(max(0., x), width-1.), y=min(max(0., y), height-1.))
                  for x, y in ((x1, y1), (x2, y2))]
        if math.hypot(points[1]['x']-points[0]['x'],points[1]['y']-points[0]['y']) < 1:
            continue
        candidates.append((length*segment['confidence'], points))
    points = max(candidates, key=lambda candidate: candidate[0])[1] if candidates else []
    if not points or image is None:
        return points
    # Find distinctive image details only in narrow end sections of the detected
    # shaft. Never search the surrounding hands/plates for an unrelated corner.
    import cv2
    import numpy as np
    a,b = (np.array([p['x'],p['y']]) for p in points)
    delta=b-a; length=float(np.linalg.norm(delta))
    band=max(2.,min(width,height)*.001)
    x0,y0=np.maximum(0,np.floor(np.minimum(a,b)-band-4)).astype(int)
    x1,y1=np.minimum([width,height],np.ceil(np.maximum(a,b)+band+5)).astype(int)
    gray=cv2.cvtColor(image[y0:y1,x0:x1],cv2.COLOR_BGR2GRAY)
    score=cv2.cornerMinEigenVal(gray,blockSize=3,ksize=3)
    yy,xx=np.mgrid[y0:y1,x0:x1]
    along=((xx-a[0])*delta[0]+(yy-a[1])*delta[1])/(length*length)
    distance=np.abs((xx-a[0])*delta[1]-(yy-a[1])*delta[0])/length
    for i,(lo,hi) in enumerate(((.01,.08),(.92,.99))):
        mask=(along>=lo)&(along<=hi)&(distance<=band)&(gray<245)
        scores=np.where(mask,score,0.)
        y,x=np.unravel_index(scores.argmax(),scores.shape)
        if scores[y,x]>=1e-4:
            points[i]=dict(x=float(x+x0),y=float(y+y0))
    return points


def seed(video, weights, device):
    import torch
    from motiontrace_ai.video_decode import VideoDecoder
    from motiontrace_ai.shaft_model import ShaftDetector
    torch.set_num_threads(4)
    decoder = VideoDecoder(video)
    try:
        timestamp, image = next(iter(decoder))
        segments = ShaftDetector(weights, device).detect(image)
        points = choose_points(segments, decoder.width, decoder.height, image)
        return dict(targetId='bar-reference', athleteTrackId=0, initializationVersion=2,
                    timestampSeconds=timestamp, points=points)
    finally:
        decoder.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()
    print(json.dumps(seed(args.input, Path(__file__).resolve().parents[1]/'models/shaft-v1.pt', args.device)))
