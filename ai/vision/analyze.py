"""MotionTrace offline vision stage. stdout is JSONL; diagnostics go to stderr."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DO_NOT_TRACK"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision import BACKEND_VERSION
from vision.config import POLICY
from vision.cache import load_cached_result, record_cache_assets


def progress(fraction, message):
    print(json.dumps(dict(type="progress", progress=max(0., min(1., fraction)), message=message)), flush=True)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def run(args):
    import torch
    from vision.pipeline import (file_hash, verify_manifest, load_corrections, detect_candidates, track_objects, classify_exercises)
    started = time.perf_counter()
    torch.set_num_threads(4)
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("Vision backend requires CUDA for the selected device; no legacy detector fallback is enabled")
    root = Path(args.models_root).resolve()
    manifest_path = root/"manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Vision models are not installed: {manifest_path}. Run setup-vision.ps1 first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    verify_manifest(root, manifest)
    for name in ("xclip", "grounding_dino", "sam2"):
        if not (root/name/"config.json").is_file() or not any((root/name).glob("*.safetensors")):
            raise FileNotFoundError(f"Missing local {name} checkpoint at {root/name}; downloads are disabled during analysis")
    pose_path = Path(args.pose_input)
    pose = json.loads(pose_path.read_text(encoding="utf-8-sig"))
    frames = pose.get("frames", [])
    if not frames:
        raise ValueError("Pose stage returned no frames")
    times = [float(f["timestampSeconds"]) for f in frames]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Pose frame timestamps must increase")
    source_hash = file_hash(args.input)
    from motiontrace_ai.video_decode import VideoDecoder, validate_analysis_frames
    validate_analysis_frames(pose)
    decoder = VideoDecoder(args.input)
    width, height = decoder.width, decoder.height
    decoder.close()
    corrections = load_corrections(args.corrections, source_hash, times, width, height,
                                   {a["id"] for a in pose.get("athletes", [])})
    source_digest = hashlib.sha256()
    for source in sorted(Path(__file__).parent.glob("*.py")):
        source_digest.update(source.name.encode())
        source_digest.update(source.read_bytes())
    decoder_source = Path(__file__).resolve().parents[1]/"motiontrace_ai"/"video_decode.py"
    source_digest.update(b"motiontrace_ai/video_decode.py")
    source_digest.update(decoder_source.read_bytes())
    from importlib.metadata import version
    dependencies = {name: version(name) for name in ("torch", "torchvision", "transformers", "numpy", "opencv-python", "av")}
    identity = dict(videoHash=source_hash, poseHash=file_hash(pose_path), backend=BACKEND_VERSION,
        models=manifest, configuration=POLICY, corrections=corrections, sourceHash=source_digest.hexdigest(),
        device=args.device, dependencies=dependencies)
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    artifact_root = Path(args.cache).resolve()/key
    progress(0., "Checking verified vision analysis cache")
    cache_started = time.perf_counter()
    cached = load_cached_result(artifact_root, key)
    if cached is not None:
        try:
            validate_analysis_frames(cached)
            if [f['timestampSeconds'] for f in cached['frames']] != times:
                cached = None
        except (ValueError, KeyError, TypeError):
            cached = None
    if cached is not None:
        if source_hash != file_hash(args.input):
            raise ValueError("Video changed while validating cached analysis")
        metadata = cached["visionMetadata"]
        metadata["originalInferencePerformance"] = metadata["performance"]
        metadata["performance"] = dict(cacheHit=True, cacheValidationSeconds=time.perf_counter()-cache_started,
                                       totalSeconds=time.perf_counter()-started, peakCudaMemoryBytes=0)
        atomic_json(args.output, cached)
        progress(1., "Vision analysis restored from verified cache")
        return
    progress(0., "Loading offline vision models")
    timings = {}
    stage = time.perf_counter()
    # Libraries occasionally write diagnostics to stdout; keep JSONL unambiguous.
    # progress explicitly targets the original protocol stream within this scope.
    protocol_stdout = sys.stdout
    def report(fraction, message):
        print(json.dumps(dict(type="progress", progress=fraction, message=message)), file=protocol_stdout, flush=True)
    with contextlib.redirect_stdout(sys.stderr):
        candidates = detect_candidates(args.input, frames, root, args.device, report)
        timings["candidateDetectionSeconds"] = time.perf_counter()-stage
        stage = time.perf_counter()
        objects = track_objects(args.input, frames, candidates, corrections, artifact_root/"masks", root, args.device, report)
        if len(objects) != len(frames):
            raise ValueError('Object tracking returned an incomplete frame timeline; analysis was not saved')
        timings["segmentationTrackingSeconds"] = time.perf_counter()-stage
        stage = time.perf_counter()
        predictions = classify_exercises(args.input, frames, candidates, root, args.device, report, objects)
        timings["exerciseClassificationSeconds"] = time.perf_counter()-stage
    if source_hash != file_hash(args.input):
        raise ValueError("Video changed during analysis; results were not saved")
    result = dict(pose)
    result["schemaVersion"] = 4
    result["frames"] = [dict(timestampSeconds=frame["timestampSeconds"], athletes=frame["athletes"],
                              shafts=[], objects=items) for frame, items in zip(frames, objects)]
    active_ids = {obj["athleteId"] for items in objects for obj in items if obj["trackingState"] == "Tracked"}
    if not active_ids:
        detected = any(row.get('candidates') for row in candidates.values())
        assigned = any(row.get('assigned') for row in candidates.values())
        reason = ('No barbell candidates detected.' if not detected else
                  'Barbell candidates could not be associated with an exercising athlete.' if not assigned else
                  'Barbell candidates were found, but tracking did not produce reliable measurements.')
        result['limitations'] = list(pose.get('limitations', [])) + [reason + ' Try object correction or the MotionTrace barbell model.']
    result["athletes"] = [dict(a, isExerciseParticipant=a["id"] in active_ids) for a in pose.get("athletes", [])]
    result["exercisePredictions"] = predictions
    from collections import Counter
    rejections = Counter(obj["rejectionReason"] for frame in objects for obj in frame if obj.get("rejectionReason"))
    result["visionMetadata"] = dict(provider="grounding_dino_sam2", backendVersion=BACKEND_VERSION,
        videoHash=source_hash, cacheKey=key, sourceHash=identity["sourceHash"], manifest=manifest, configuration=POLICY,
        coordinateSystem=POLICY["coordinateSystem"], corrections=corrections, candidateFrames=candidates,
        dependencies=dependencies,
        rejectedObjectFrameCounts=dict(rejections),
        measurementWarning="Mask position is an object proxy, not a validated shaft-axis measurement. Manual points use checked optical flow.",
        performance=dict(timings, cacheHit=False, totalSeconds=time.perf_counter()-started,
                         peakCudaMemoryBytes=torch.cuda.max_memory_allocated() if torch.cuda.is_available() else 0))
    result["versions"] = dict(pose.get("versions", {}), engineVersion=BACKEND_VERSION,
                              barbellProvider="grounding_dino_sam2", measurementVersion=POLICY["measurementMethod"])
    result["engineVersion"] = BACKEND_VERSION
    atomic_json(artifact_root/"result.json", result)
    record_cache_assets(artifact_root, result, key, atomic_json)
    atomic_json(args.output, result)
    progress(1., "Vision analysis complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "pose-input", "output", "cache", "models-root"):
        parser.add_argument("--"+name, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--corrections")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
