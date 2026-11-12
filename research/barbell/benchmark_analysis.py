"""Full-engine wall time and stage profiles on fixed, untrimmed videos."""
import argparse,json,subprocess,sys,time
from pathlib import Path

root=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--engine',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--sync',action='store_true')
parser.add_argument('--cache',help='Reuse pose cache when evaluating shaft changes.')
args=parser.parse_args()
out=root/args.output
out.mkdir(parents=True,exist_ok=False)
records=json.loads((root/'research/barbell/phase_annotations.json').read_text(encoding='utf-8'))['records']
results=[]
for record in [records[0],records[3],records[5]]:
    name=record['video_id'];started=time.perf_counter()
    command=[sys.executable,str(root/args.engine),'--input',str(root/record['source']),
             '--output',str(out/(name+'.json')),'--cache',str(root/args.cache if args.cache else out/'cache'),'--device','cuda:0',
             '--profile-output',str(out/(name+'.profile.json'))]
    if args.sync:command.append('--synchronous-decode')
    print('START '+record['source'],flush=True)
    with (out/(name+'.progress.log')).open('w') as stdout,(out/(name+'.stderr.log')).open('w') as stderr:
        subprocess.run(command,cwd=root,stdout=stdout,stderr=stderr,check=True)
    results.append(dict(video=record['source'],id=name,wallSeconds=time.perf_counter()-started))
    (out/'timings.json').write_text(json.dumps(results,indent=2))
    print(results[-1],flush=True)
