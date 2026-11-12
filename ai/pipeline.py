"""Sequential local process boundary: existing pose Python, then isolated vision Python."""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1')


def progress(stage,fraction=0):
    print(json.dumps(dict(stage=stage,fraction=fraction)),flush=True)


def default_models_root():
    for parent in Path(__file__).resolve().parents:
        candidate = parent/'.models/vision'
        if (candidate/'manifest.json').is_file():return str(candidate)
    return str(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'MotionTrace/models/vision')


def run_stage(command,start,end):
    env=os.environ.copy();directory=str(Path(command[0]).parent)
    env['PATH']=directory+os.pathsep+str(Path(directory)/'Library/bin')+os.pathsep+env.get('PATH','')
    env['PYTHONIOENCODING']='utf-8'
    # No console of its own: every stage starts a new Python process, and a console window (even a hidden one)
    # makes Windows play its notification sound.
    with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',env=env,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as child:
        error_tail=deque(maxlen=8)
        def errors():
            for line in child.stderr:
                sys.stderr.write(line)
                if line.strip():error_tail.append(line.strip())
        reader=threading.Thread(target=errors,daemon=True);reader.start()
        try:
            for line in child.stdout:
                try:
                    record=json.loads(line)
                    if 'stage' in record:
                        fraction=record.get('fraction')
                        progress(record['stage'],start+(end-start)*float(fraction or 0))
                    elif record.get('type')=='progress':
                        progress(record.get('message','Analyzing'),start+(end-start)*float(record.get('progress') or 0))
                    else:sys.stderr.write(line)
                except (ValueError,TypeError):sys.stderr.write(line)
            code=child.wait();reader.join()
            if code:
                cause=error_tail[-1] if error_tail else 'The backend did not report a cause; see the MotionTrace log.'
                raise RuntimeError(f'{Path(command[1]).name} failed (exit {code}): {cause}')
        except BaseException:
            child.kill();child.wait();reader.join();raise


def custom_classifier_available(interpreter, models_root):
    root = Path(models_root)
    return (Path(interpreter).is_file() and (root/'manifest.json').is_file()
            and (root/'xclip/config.json').is_file() and any((root/'xclip').glob('*.safetensors')))


def analyze(args):
    root=Path(__file__).resolve().parent
    if args.provider=='custom_barbell' and not (root/'models/shaft-v1.pt').is_file():
        raise FileNotFoundError('Custom barbell model is missing: '+str(root/'models/shaft-v1.pt'))
    if args.provider=='grounding_dino_sam2':
        if not Path(args.vision_python).is_file():raise FileNotFoundError('Vision Python is missing. Run scripts/setup-vision.ps1 first: '+args.vision_python)
        if not (Path(args.models_root)/'manifest.json').is_file():raise FileNotFoundError(f'Vision model manifest was not found at: {Path(args.models_root).resolve()/"manifest.json"}. Check ModelsRoot in settings.json or run scripts/setup-vision.ps1 if models have not been installed.')
    cache=Path(args.cache);cache.mkdir(parents=True,exist_ok=True)
    progress('Checking local model setup')
    with tempfile.TemporaryDirectory(prefix='pose-stage-',dir=cache) as temporary:
        pose_output=Path(temporary)/'pose.json'
        command=[sys.executable,'-u',str(root/'analyze.py'),'--input',args.input,'--output',str(pose_output),
                 '--cache',str(cache/'pose'),'--device',args.device,'--pose-model',args.pose_model,
                 '--pose-weights',args.pose_weights,'--crop-padding',str(args.crop_padding),
                 '--barbell-provider','custom_barbell' if args.provider=='custom_barbell' else 'pose_only']
        classify_custom = args.provider == 'custom_barbell' and custom_classifier_available(args.vision_python, args.models_root)
        run_stage(command,0,.35 if args.provider!='custom_barbell' else (.8 if classify_custom else 1))
        if args.provider=='custom_barbell':
            if classify_custom:
                run_stage([args.vision_python, '-u', str(root/'vision/classify_custom.py'),
                    '--input', args.input, '--pose-input', str(pose_output), '--output', args.output,
                    '--cache', str(cache/'custom-exercise'), '--models-root', args.models_root, '--device', args.device], .8, 1)
                progress('Analysis ready', 1)
                return
            result=json.loads(pose_output.read_text(encoding='utf-8'))
            result['provider']='custom_barbell'
            result['exerciseClassificationMetadata'] = dict(provider='none', status='unavailable',
                reason='Optional local X-CLIP environment/checkpoint is not installed; select exercise manually.')
            result['limitations'] = list(result.get('limitations', [])) + [result['exerciseClassificationMetadata']['reason']]
            Path(args.output).parent.mkdir(parents=True,exist_ok=True)
            Path(args.output).write_text(json.dumps(result,separators=(',',':')),encoding='utf-8')
            return
        command=[args.vision_python,'-u',str(root/'vision/analyze.py'),'--input',args.input,
                 '--pose-input',str(pose_output),'--output',args.output,'--cache',str(cache/'vision'),
                 '--models-root',args.models_root,'--device',args.device]
        if args.corrections:command+=['--corrections',args.corrections]
        run_stage(command,.35,1)
    progress('Analysis ready',1)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('input','output','cache'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--vision-python',default=str(Path.home()/'miniconda3/envs/motiontrace-vision/python.exe'))
    parser.add_argument('--models-root',default=default_models_root())
    parser.add_argument('--provider',choices=('grounding_dino_sam2','custom_barbell'),default='grounding_dino_sam2')
    parser.add_argument('--device',default='cuda:0')
    parser.add_argument('--pose-model',default='rtmpose-l_8xb256-420e_body8-384x288')
    parser.add_argument('--pose-weights',default='')
    parser.add_argument('--crop-padding',type=float,default=.2)
    parser.add_argument('--corrections')
    try:analyze(parser.parse_args())
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
