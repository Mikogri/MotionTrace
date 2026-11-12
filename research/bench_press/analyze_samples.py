import sys, os
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'ai'))
from analyze import analyze
from argparse import Namespace
for name in ['VID_20251014_204427~2.mp4','VID_20260424_214030~2.mp4','100kg x 5.mp4']:
    print('DATASET '+name,flush=True)
    analyze(Namespace(input=str(root/'videos/bench'/name),output=str(root/'artifacts/bench_dataset'/(name+'.json')),cache=str(root/'artifacts/bench_dataset/cache'),device='cuda:0'))
