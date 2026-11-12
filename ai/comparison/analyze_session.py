"""One local session, shared preparation, four independent resource-budgeted jobs."""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from comparison.scheduler import PROVIDERS, schedule, resources, job_budget
from vision.analyze import atomic_json
from vision.cache import file_digest

os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1')
STOP=threading.Event()
LOCK=threading.Lock()


def network_video(path):
    if str(path).startswith('\\\\'):
        return True
    if os.name == 'nt':
        import ctypes
        import ntpath
        drive = ntpath.splitdrive(os.path.abspath(path))[0]
        return bool(drive) and ctypes.windll.kernel32.GetDriveTypeW(drive+'\\') == 4
    return False


def local_video_copy(source, cache, expected_hash):
    """Stage one verified input so later passes do not depend on an SMB connection."""
    destination = Path(cache).resolve()/'inputs'/expected_hash/Path(source).name
    if destination.is_file() and file_digest(destination) == expected_hash:
        return str(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        digest = hashlib.sha256()
        with open(source, 'rb') as incoming, open(temporary, 'wb') as outgoing:
            while block := incoming.read(1024*1024):
                if STOP.is_set():
                    raise RuntimeError('Analysis cancelled')
                outgoing.write(block)
                digest.update(block)
        if digest.hexdigest() != expected_hash:
            raise ValueError('Video changed during copying; select the file again.')
        os.replace(temporary, destination)
        return str(destination)
    except OSError as error:
        raise RuntimeError('Cannot read the network video. Reconnect the drive or copy the film to a local disk and select it again.') from error
    finally:
        temporary.unlink(missing_ok=True)


def emit(stage, **fields):
    with LOCK:
        print(json.dumps(dict(stage=stage,**fields)),flush=True)


def process_error(command, returncode, tail):
    script = next((Path(arg).name for arg in command[1:] if str(arg).endswith('.py')), Path(command[0]).name)
    code = returncode & 0xffffffff
    if code == 0xc0000005:
        return (f'{script}: native library crashed (0xC0000005, access violation). '
                'Check available RAM/page file and the analysis log; this is not a tracking result.')
    return tail[-1] if tail else f'{script} exited with code {returncode}'


def process(command, provider=None):
    env=os.environ.copy(); directory=str(Path(command[0]).parent)
    env['PATH']=directory+os.pathsep+str(Path(directory)/'Library/bin')+os.pathsep+env.get('PATH','')
    env['PYTHONIOENCODING']='utf-8'
    env['PYTHONFAULTHANDLER']='1'
    tail=deque(maxlen=12)
    # No console of its own: every stage starts a new Python process, and a console window (even a hidden one)
    # makes Windows play its notification sound.
    with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',env=env,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as child:
        def stderr():
            for line in child.stderr:
                sys.stderr.write(line)
                if line.strip():tail.append(line.strip())
        def stdout():
            for line in child.stdout:
                try:
                    data=json.loads(line)
                    emit(data.get('stage',data.get('message','Analyzing')),providerId=provider,
                         fraction=data.get('fraction',data.get('progress')))
                except (ValueError,AttributeError):sys.stderr.write(line)
        readers=[threading.Thread(target=f,daemon=True) for f in (stderr,stdout)]
        for reader in readers:reader.start()
        while child.poll() is None:
            if STOP.wait(.1):
                child.kill();child.wait();break
        for reader in readers:reader.join()
        if STOP.is_set() and child.returncode != 0:raise RuntimeError('Analysis cancelled')
        if child.returncode:
            # stderr has already been forwarded to the application log. Show the
            # actual final exception in the small banner, not twelve stack frames.
            raise RuntimeError(process_error(command, child.returncode, tail))


def receipt(path):
    result=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    assets={str(Path(path).resolve()):file_digest(path)}
    if result.get('rawObservationsPath'):
        raw = Path(result['rawObservationsPath'])
        if not raw.is_absolute():raw=Path(path).parent/raw
        assets[str(raw.resolve())]=file_digest(raw)
    for frame in result.get('frames',[]):
        for obj in frame.get('objects',[]):
            mask=obj.get('maskPath')
            if mask:
                mask=Path(mask)
                if not mask.is_absolute():mask=Path(path).parent/mask
                assets[str(mask.resolve())]=file_digest(mask)
    return assets


def valid_assets(assets):
    try:return bool(assets) and all(Path(p).is_file() and file_digest(p)==digest for p,digest in assets.items())
    except (OSError,TypeError,AttributeError):return False


def code_identity(root):
    return {str(p.relative_to(root)):file_digest(p) for folder in ('comparison','vision','motiontrace_ai') for p in sorted((root/folder).glob('*.py'))}


def load_resident_weights(checkpoint, device, resolution):
    """Build the pinned architecture without random weight allocation or a second CPU weight copy."""
    import torch
    from tapnet.tapnext import tapnext_torch
    from tapnet.tapnextpp.votsp2026.model import TAPNextPP
    with torch.device('meta'):
        inner = tapnext_torch.TAPNext(image_size=(TAPNextPP.MODEL_SIZE, TAPNextPP.MODEL_SIZE))
    checkpoint_data = torch.load(checkpoint, map_location='cpu', weights_only=True, mmap=True)
    state = {k.removeprefix('tapnext.'): v for k, v in checkpoint_data.get('state_dict', checkpoint_data).items()}
    expected = inner.state_dict()
    for name, value in state.items():
        target = expected.get(name)
        if target is not None and (value.dtype != target.dtype or value.stride() != target.stride()):
            raise ValueError('Checkpoint dtype/layout differs from the reviewed model architecture')
    inner.load_state_dict(state, strict=True, assign=True)
    inner = inner.to(device).eval()
    return TAPNextPP(inner, torch.device(device), input_resolution=resolution)


class ResidentTracker:
    """One verified weight set, never recurrent state or observations from a previous video."""
    def __init__(self, root=None):
        self.model = self.key = None
        self.gpu_mib = 0
        self.sources = code_identity(root) if root else None

    def clear(self):
        import gc
        self.model = self.key = None
        self.gpu_mib = 0
        gc.collect()
        torch = sys.modules.get('torch')
        if torch is not None and torch.cuda.is_initialized():
            torch.cuda.empty_cache()

    def load(self, checkpoint, device, resolution):
        key = (str(Path(checkpoint).resolve()), device, resolution)
        if self.key != key:
            self.clear()
            import torch
            before = torch.cuda.memory_allocated(device) if str(device).startswith('cuda') else 0
            self.model = load_resident_weights(checkpoint, device, resolution)
            self.key = key
            if str(device).startswith('cuda'):
                self.gpu_mib = max(0, torch.cuda.memory_allocated(device) - before) // (1024 * 1024)
        return self.model

    def track(self, *args, **kwargs):
        from comparison import tap_backends
        failure = None
        try:
            return tap_backends.run(*args, **kwargs, model_loader=self.load)
        except Exception as error:
            import traceback
            traceback.print_exc(file=sys.stderr)
            failure = str(error)
        # Drop exception frames before releasing CUDA memory, including the scheduler's OOM retry.
        self.clear()
        raise RuntimeError(failure)

    def remaining_budget(self, job):
        return dict(job, gpuMiB=max(0, job['gpuMiB'] - self.gpu_mib))


def inference_identity(args, target, root, model_roots, interpreters):
    inference_target={k:v for k,v in target.items() if k not in ('calibration','calibrationVersion')}
    sources=code_identity(root)
    weights=Path(args.pose_weights) if args.pose_weights else None
    pose_config=Path(args.pose_model)
    return dict(videoHash=file_digest(args.input),target=inference_target,sources=sources,
        models={p:file_digest(Path(r)/'manifest.json') if (Path(r)/'manifest.json').is_file() else None for p,r in model_roots.items()},
        poseModel=args.pose_model,poseConfigHash=file_digest(pose_config) if pose_config.is_file() else None,
        poseWeights=args.pose_weights,poseWeightsHash=file_digest(weights) if weights and weights.is_file() else None,
        cropPadding=args.crop_padding,device=args.device,interpreters=interpreters,posePython=args.pose_python,
        tapnextResolution=getattr(args,'tapnext_resolution',256),
        tapnextCheckpoint=getattr(args,'tapnext_checkpoint',None),
        tapnextCheckpointHash=file_digest(args.tapnext_checkpoint) if getattr(args,'tapnext_checkpoint',None) and Path(args.tapnext_checkpoint).is_file() else None,
        classificationManifestHash=file_digest(Path(args.models_root)/'manifest.json') if (Path(args.models_root)/'manifest.json').is_file() else None,
        pointsOnly=bool(getattr(args,'points_only',False)))


def current_calibration(resolved_target, requested_target):
    target=dict(resolved_target)
    for field in ('calibration','calibrationVersion'):
        if field in requested_target:target[field]=requested_target[field]
        else:target.pop(field,None)
    return target


def run(args, resident=None):
    root=Path(__file__).resolve().parents[1]
    target=json.loads(Path(args.target).read_text(encoding='utf-8-sig'))
    two_points = 'points' in target
    if resident is not None and (not two_points or not getattr(args, 'points_only', False)):
        raise ValueError('The resident worker accepts only the two-point pipeline')
    if two_points:
        from comparison.tap_backends import target_points, installation
        target_points(target)
        # Reject the wrong model/resolution before spending time on pose extraction.
        checkpoint, _ = installation(args.points_models_root,'tapnextpp',getattr(args,'tapnext_resolution',256),
                                     getattr(args,'tapnext_checkpoint',None))
        if resident is not None and resident.key != (str(Path(checkpoint).resolve()), args.device, getattr(args,'tapnext_resolution',256)):
            resident.clear()
    elif not target.get('point'):raise ValueError('Mark the physical bar end / plate axis before Analyze.')
    providers = ('tapnextpp',) if two_points else PROVIDERS
    interpreters=dict(grounding_dino_sam2=args.vision_python,samurai=args.samurai_python,tapnextpp=args.points_python,bootstapir=args.points_python)
    model_roots=dict(grounding_dino_sam2=args.models_root,samurai=args.samurai_models_root,tapnextpp=args.points_models_root,bootstapir=args.points_models_root)
    if two_points:
        interpreters = {p:interpreters[p] for p in providers}
        model_roots = {p:model_roots[p] for p in providers}
    # Calibration changes affect prepared metrics, not tracking inference.
    identity=inference_identity(args,target,root,model_roots,interpreters)
    if resident is not None and resident.sources is not None and resident.sources != identity['sources']:
        raise RuntimeError('Analyzer sources changed; restart the worker before retrying')
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    directory=Path(args.cache).resolve()/'comparisons'/key;directory.mkdir(parents=True,exist_ok=True)
    manifest_path=directory/'session.json'
    previous=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}
    rows={r['providerId']:r for r in previous.get('providers',[])}
    manifest=dict(schemaVersion=1,sessionId=key,videoPath=str(Path(args.input).resolve()),identity=identity,
        target=current_calibration(previous.get('target',target),target),providers=[],
        scheduling=dict(policy='live-free-memory-reservations',initialResources=resources()))
    def save():
        manifest['providers']=[rows[p] for p in providers]
        atomic_json(manifest_path,manifest);atomic_json(args.output,manifest)
    requested=set(args.providers.split(',')) if args.providers else set(PROVIDERS)
    if not requested<=set(PROVIDERS):raise ValueError('Unknown comparison provider')
    if two_points:requested={'tapnextpp'}
    jobs=[]
    for provider in providers:
        old=rows.get(provider,{})
        if old.get('status') in ('TrackingReady','Ready') and valid_assets(old.get('assets')):
            rows[provider]=dict(old,status='TrackingReady')
        elif provider not in requested:
            rows[provider]=dict(old) if old.get('status') in ('Failed','Cancelled','NotInstalled','Stale') else dict(providerId=provider,status='NotAnalyzed',error=old.get('error'))
        elif not Path(interpreters[provider]).is_file() or not (Path(model_roots[provider])/'manifest.json').is_file():
            rows[provider]=dict(providerId=provider,status='NotInstalled',error='Run the matching tracker setup script; no fallback was started.')
        else:
            rows[provider]=dict(providerId=provider,status='Queued')
            jobs.append(dict(providerId=provider))
    save()
    for provider,row in rows.items():emit(f'{provider}: {row["status"]}',**{k:v for k,v in row.items() if k in ('providerId','status','resultPath','error')})
    if not jobs:
        emit('Session complete',fraction=1,sessionPath=str(manifest_path))
        return
    prepared=directory/'shared.json';resolved=directory/'target.json';shared_receipt=directory/'shared-receipt.json'
    shared_assets=json.loads(shared_receipt.read_text()) if shared_receipt.is_file() else {}
    try:
        if network_video(args.input):
            emit('Copying network video to local analysis cache')
            args = argparse.Namespace(**vars(args))
            args.input = local_video_copy(args.input, args.cache, identity['videoHash'])
        if not valid_assets(shared_assets) and two_points and getattr(args,'points_only',False):
            # Points only: no lifter detection and no exercise classification; the marked points are all that is measured.
            emit('Preparing the video timeline (points only)')
            if resident is None:
                process([args.vision_python,'-u',str(root/'comparison/points_prepare.py'),'--input',args.input,'--target',args.target,
                    '--resolved-target',str(resolved),'--output',str(prepared)])
            else:
                from comparison import points_prepare
                points_prepare.run(argparse.Namespace(input=args.input, target=args.target,
                    resolved_target=str(resolved), output=str(prepared)))
            atomic_json(shared_receipt,{str(prepared):file_digest(prepared),str(resolved):file_digest(resolved)})
        elif not valid_assets(shared_assets):
            pose=directory/'pose.json'
            emit('Shared RTMPose preparation (once)')
            process([args.pose_python,'-u',str(root/'analyze.py'),'--input',args.input,'--output',str(pose),
                '--cache',str(Path(args.cache)/'pose'),'--barbell-provider','pose_only','--device',args.device,
                '--pose-model',args.pose_model,'--pose-weights',args.pose_weights,'--crop-padding',str(args.crop_padding)])
            emit('Shared physical target and exercise classification (once)')
            process([args.vision_python,'-u',str(root/'comparison/prepare.py'),'--input',args.input,'--pose-input',str(pose),
                '--target',args.target,'--resolved-target',str(resolved),'--output',str(prepared),'--models-root',args.models_root,
                '--device',args.device,'--cache',str(Path(args.cache))])
            atomic_json(shared_receipt,{str(prepared):file_digest(prepared),str(resolved):file_digest(resolved)})
        manifest['target']=current_calibration(json.loads(resolved.read_text()),target)
        shared=json.loads(prepared.read_text(encoding='utf-8-sig'))
        from motiontrace_ai.video_decode import validate_analysis_frames
        validate_analysis_frames(shared)
        jobs=[job_budget(job['providerId'],len(shared['frames'])) for job in jobs]
        if resident is not None:
            # Already allocated weights are absent from free VRAM: count only the remaining job budget.
            jobs = [resident.remaining_budget(job) for job in jobs]
        save()
        def execute(job):
            provider=job['providerId']; out=directory/provider/'analysis.json';out.parent.mkdir(parents=True,exist_ok=True)
            script='dino_backend.py' if provider=='grounding_dino_sam2' else 'samurai_backend.py' if provider=='samurai' else 'tap_backends.py'
            command=[interpreters[provider],'-u',str(root/'comparison'/script),'--input',args.input,'--pose-input',str(prepared),
                '--target',str(resolved),'--output',str(out),'--models-root',model_roots[provider],'--device',args.device]
            if provider in ('tapnextpp','bootstapir'):command+=['--provider',provider]
            if provider == 'tapnextpp':
                command+=['--tapnext-resolution',str(getattr(args,'tapnext_resolution',256))]
                if getattr(args,'tapnext_checkpoint',None):command+=['--tapnext-checkpoint',args.tapnext_checkpoint]
            started=time.perf_counter()
            if resident is None:
                process(command,provider)
            else:
                resident.track(provider, args.input, str(prepared), str(resolved), str(out), model_roots[provider],
                    args.device, lambda value, message: emit(message, fraction=value, providerId=provider),
                    tapnext_resolution=getattr(args,'tapnext_resolution',256),
                    tapnext_checkpoint=getattr(args,'tapnext_checkpoint',None))
            if file_digest(args.input)!=identity['videoHash']:raise ValueError('Video changed during analysis')
            tracking=json.loads(out.read_text(encoding='utf-8-sig'))
            validate_analysis_frames(tracking)
            if (tracking.get('provider')!=provider or len(tracking['frames'])!=len(shared['frames'])
                    or any(abs(a['timestampSeconds']-b['timestampSeconds'])>.001 for a,b in zip(tracking['frames'],shared['frames']))):
                raise ValueError('Tracker result has a wrong provider or incomplete/shared timeline mismatch')
            assets=receipt(out)
            return dict(resultPath=str(out),assets=assets,elapsedSeconds=time.perf_counter()-started)
        def report(provider,status,value):
            row=dict(providerId=provider,status=status)
            if status=='TrackingReady':row.update(value)
            elif value:row['error']=str(value)
            rows[provider]=row;save()
            emit(f'{provider}: {status}',**{k:v for k,v in row.items() if k in ('providerId','status','resultPath','error')})
        schedule(jobs,execute,report,STOP.is_set)
    except Exception as exc:
        for provider,row in rows.items():
            if row['status'] in ('Queued','Running'):
                row.update(status='Cancelled' if STOP.is_set() else 'Failed',error=str(exc))
                emit(str(exc),providerId=provider,status=row['status'],error=str(exc))
        save()
    emit('Session complete',fraction=1,sessionPath=str(manifest_path))


def parser():
    p=argparse.ArgumentParser()
    for name in ('input','output','cache','target','pose-python','vision-python','samurai-python','points-python','models-root','samurai-models-root','points-models-root'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--device',default='cuda:0');p.add_argument('--providers',default='')
    p.add_argument('--pose-model',default='rtmpose-l_8xb256-420e_body8-384x288');p.add_argument('--pose-weights',default='')
    p.add_argument('--crop-padding',type=float,default=.2)
    p.add_argument('--tapnext-resolution',type=int,choices=(256,512),default=256)
    p.add_argument('--tapnext-checkpoint',default=None)
    p.add_argument('--points-only',action='store_true',help='Two-point tracking without pose detection or exercise classification')
    return p


def worker_loop():
    resident = ResidentTracker(Path(__file__).resolve().parents[1])
    try:
        for line in sys.stdin:
            request = None
            try:
                command = json.loads(line)
                request = command['request']
                arguments = parser().parse_args(command['arguments'])
                if Path(arguments.points_python).resolve() != Path(sys.executable).resolve():
                    raise ValueError('The resident worker must run in the configured points environment')
                STOP.clear()
                run(arguments, resident)
                manifest = json.loads(Path(arguments.output).read_text(encoding='utf-8-sig'))
                ok = all(row['status'] in ('Ready','TrackingReady') for row in manifest['providers'])
                torch = sys.modules.get('torch')
                if torch is not None and torch.cuda.is_initialized():
                    torch.cuda.empty_cache()  # Keep weights, release per-video allocator scratch.
                print(json.dumps(dict(workerRequest=request, ok=ok)), flush=True)
                if not ok:
                    return
            except (Exception, SystemExit):
                import traceback
                traceback.print_exc(file=sys.stderr)
                print(json.dumps(dict(workerRequest=request, ok=False)), flush=True)
                return
    finally:
        resident.clear()


if __name__=='__main__':
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:STOP.set())
    if sys.argv[1:] == ['--worker']:
        worker_loop()
        sys.exit(0)
    try:run(parser().parse_args())
    except Exception:
        import traceback;traceback.print_exc(file=sys.stderr);sys.exit(1)
