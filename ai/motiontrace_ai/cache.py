"""Only inference configuration belongs in a reusable cache key."""
import hashlib
import json
import math
from pathlib import Path


def inference_configuration(config):
    # MMDetection mutates visualizer.name to include wall-clock time at startup.
    # Visualization is disabled in MotionTrace, so this is neither model nor inference state.
    copy = config.copy()
    copy.pop('visualizer', None)
    try:
        # Formatting a large config as Python invokes YAPF. A canonical JSON
        # representation has the same cache purpose without formatting work.
        return json.dumps(copy.to_dict(),sort_keys=True,separators=(',',':'),allow_nan=False)
    except (TypeError,ValueError):
        # Preserve support for custom configs containing Python objects.
        return copy.pretty_text


def pose_fingerprint(fingerprint):
    """Shaft code/weights and presentation changes cannot invalidate person poses."""
    adapters=('pose_pipeline.py','mapping.py','person_tracking.py','tracking.py','video_decode.py')
    return {**{k:fingerprint[k] for k in ('model','cropPadding','selected','tracker','device','video',
                                        'pose','detector','configuration','detectorConfiguration','packages')},
            'poseCacheSchema':1,
            'adapter':{k:v for k,v in fingerprint['adapter'].items() if k.replace('\\','/').split('/')[-1] in adapters}}


def cache_key(fingerprint):
    return hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()


def configuration_sources(roots):
    """Hash installed config trees, including inherited bases, without loading models."""
    digest=hashlib.sha256()
    for root in roots:
        root=Path(root)
        files=sorted(p for p in root.rglob('*') if p.is_file() and p.suffix in ('.py','.yml','.yaml','.json'))
        if not files:return None  # Unusual/custom installations use the normal model-aware lookup.
        for path in files:
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def read_pose_cache(path,key):
    """A digest sidecar rejects interrupted writes and accidental cache corruption."""
    try:
        data=path.read_bytes()
        manifest=json.loads(path.with_suffix('.sha256.json').read_text(encoding='utf-8'))
        if not isinstance(manifest,dict) or manifest.get('key')!=key or manifest.get('sha256')!=hashlib.sha256(data).hexdigest():return None
        result=json.loads(data)
        if not isinstance(result,dict) or result.get('schema')!=1 or not isinstance(result.get('confirmedIds'),list):return None
        frames=result.get('frames')
        if not isinstance(frames,list) or not frames:return None
        previous=-1
        for frame in frames:
            timestamp=frame['timestampSeconds']
            if not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp) or timestamp<=previous:return None
            if not isinstance(frame['athletes'],list):return None
            previous=timestamp
        return result
    except (OSError,ValueError,KeyError,TypeError):
        return None
