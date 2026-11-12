"""Pinned official TAPNext++ / offline BootsTAPIR point trackers. No downloads."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REVISION = "730cda1c730877cfedbe01bf87fb1cadb78a565d"
WEIGHT_REVISION = "5d3fb48e76c5422841e38501514121e251beabb7"
CHECKPOINTS = {
    "tapnextpp": ("tapnextpp_ckpt.pt", "cb96a43444ccb4fbdb25d800b88c7ba196179a526e78f01b021a16b1c1eff6da", 2532282370),
    "bootstapir": ("bootstapir_checkpoint_v2.pt", "8493c7a69e02c85b9382fbb3c7b8b539b36bc08ede744b9e99feb739a0129f4b", 218886140),
}
VERSION = "tap-points-8"
TAPNEXT_CHECKPOINTS = {
    256: CHECKPOINTS['tapnextpp'],
    512: ('tapnextpp_512.ckpt', '6cd0e793fdcface3063d63f8ed3819bcf74c2c0468fe1fef85acee4de2f3609f', 2532283010),
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def installation(root, provider, resolution=256, checkpoint_path=None):
    root = Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("repositoryRevision") != REVISION:
        raise ValueError("TAP code revision mismatch; run scripts/setup-tap-trackers.ps1")
    entry = manifest["models"][provider]
    if resolution not in TAPNEXT_CHECKPOINTS or (provider != 'tapnextpp' and resolution != 256):
        raise ValueError('Unsupported tracker resolution')
    filename, expected, size = TAPNEXT_CHECKPOINTS[resolution] if provider == 'tapnextpp' else CHECKPOINTS[provider]
    checkpoint = Path(checkpoint_path).resolve() if checkpoint_path else root / filename
    if checkpoint.stat().st_size != size or sha256(checkpoint) != expected:
        raise ValueError(f"Invalid {provider} checkpoint; run scripts/setup-tap-trackers.ps1")
    for source in manifest.get("sourceFiles", []):
        path = (root / source["path"]).resolve()
        if not path.is_relative_to(root) or sha256(path) != source["sha256"]:
            raise ValueError("TAP source integrity check failed")
    if not manifest.get("sourceFiles"):
        raise ValueError("TAP installation has no source integrity manifest")
    sys.path.insert(0, str(root / "tapnet"))
    return checkpoint, entry


def target_points(target):
    if 'points' not in target:
        return [target.get('point')]
    points = target['points']
    if not isinstance(points, list) or len(points) != 2:
        raise ValueError('Mark exactly two distinct physical points on the same video frame')
    if any(not isinstance(p, dict) or any(isinstance(p.get(k), bool) or not isinstance(p.get(k), (int, float)) or not math.isfinite(p[k]) for k in ('x','y')) for p in points):
        raise ValueError('Both physical points must have finite numeric coordinates')
    if (points[0]['x'],points[0]['y']) == (points[1]['x'],points[1]['y']):
        raise ValueError('Mark exactly two distinct physical points on the same video frame')
    return points


def validate_target(pose, target):
    frames = pose["frames"]
    width, height = pose["video"]["width"], pose["video"]["height"]
    index = target["frameIndex"]
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(frames):
        raise ValueError("Target frameIndex is outside the shared timeline")
    if abs(target["timestampSeconds"] - frames[index]["timestampSeconds"]) > .001:
        raise ValueError("Target frameIndex and timestamp do not match")
    for point in target_points(target):
        if not isinstance(point, dict) or not all(not isinstance(point.get(k), bool) and isinstance(point.get(k), (int, float)) and math.isfinite(point[k]) for k in ("x", "y")):
            raise ValueError("A finite physical reference point is required")
        if not (0 <= point["x"] < width and 0 <= point["y"] < height):
            raise ValueError("Reference point is outside the video")
    if not target.get("targetId") or target.get("athleteTrackId", 0) <= 0:
        raise ValueError("A resolved athlete and target identity are required")
    return index


def observation(target, provider, x, y, visible, raw, width, height, point_index=None):
    finite = math.isfinite(x) and math.isfinite(y)
    valid = finite and visible and 0 <= x < width and 0 <= y < height
    measurement = None
    if valid:
        measurement = dict(x=x, y=y, source=provider, quality="Reduced",
                           isProxy=False, isInterpolated=False, isManualCorrection=False)
    result = dict(objectId=target["targetId"] if point_index is None else f'{target["targetId"]}-{point_index + 1}', athleteId=target["athleteTrackId"],
                box=None, maskPath=None, confidence=max(0., min(1., raw["visibilityProbability"])),
                scoreMeaning="model visibility probability, not cross-model calibrated confidence",
                trackingState="Tracked" if valid else "Lost",
                measurement=measurement, rawObservation=dict(x=x if finite else None,
                    y=y if finite else None, visible=bool(visible), **raw),
                rejectionReason=None if valid else "occluded-uncertain-or-outside-image")
    if point_index is not None:
        result.update(measurementGroupId=target['targetId'], pointIndex=point_index)
    return result


def decoded_frames(video, pose):
    from motiontrace_ai.video_decode import PrefetchedVideoDecoder
    # The bounded producer decodes the next frame while inference uses the GPU.
    # Every presentation timestamp is still validated; no frames are skipped.
    decoder = PrefetchedVideoDecoder(video, capacity=2)
    expected = pose["frames"]
    count = 0
    try:
        if (decoder.width, decoder.height) != (pose["video"]["width"], pose["video"]["height"]):
            raise ValueError("Decoded image dimensions differ from the shared pose")
        for index, (timestamp, image) in enumerate(decoder):
            if index >= len(expected) or abs(timestamp - expected[index]["timestampSeconds"]) > .001:
                raise ValueError("Video timestamps differ from the shared pose timeline")
            count += 1
            yield index, image
        if count != len(expected):
            raise ValueError(f"Incomplete video decode: {count}/{len(expected)} frames")
    finally:
        decoder.close()


def tracking_region(target, width, height, pose=None):
    """Fixed source-space context; never move a crop under recurrent model state."""
    if 'points' not in target:
        return 0, 0, width, height
    points = target_points(target)
    # Points-only has no pose-derived motion envelope. A seed-centred crop can exclude
    # the floor or overhead part of the very lift we are trying to recover backwards.
    if pose is not None and not any(frame.get('athletes') for frame in pose.get('frames', [])):
        return 0, 0, width, height
    span = math.hypot(points[1]['x']-points[0]['x'], points[1]['y']-points[0]['y'])
    side = math.ceil(max(3 * span, .6 * min(width, height)))
    center = [sum(p[k] for p in points)/2 for k in ('x','y')]
    # Pose only bounds a fixed context window; it never supplies measurements.
    # Require two confident wrists near the initial bar and dense coverage.
    frames = (pose or {}).get('frames', [])[target.get('frameIndex',0):]
    wrists = []
    for i,frame in enumerate(frames):
        for person in frame.get('athletes',[]):
            if person['athleteId'] != target.get('athleteTrackId') or person['trackingState'] != 'Tracked':
                continue
            pair = [k for k in person['keypoints'] if k['joint'] in ('LeftWrist','RightWrist') and k['confidence'] >= .7]
            if len(pair) == 2:
                wrists.append((i, [sum(p[k] for p in pair)/2 for k in ('x','y')]))
    if (len(wrists) >= max(20,len(frames)*.8) and wrists[0][0] == 0
            and math.dist(center,wrists[0][1]) <= min(width,height)*.15):
        reference=wrists[0][1]
        projected=[[p[k]+w[j]-reference[j] for j,k in enumerate(('x','y'))] for _,w in wrists for p in points]
        low=[min(p[j] for p in projected) for j in range(2)]
        high=[max(p[j] for p in projected) for j in range(2)]
        side=math.ceil(max(.5*min(width,height),max(high[j]-low[j] for j in range(2))+.24*min(width,height)))
        center=[(low[j]+high[j])/2 for j in range(2)]
    w, h = min(side, width), min(side, height)
    x = min(max(0, round(center[0]-w/2)), width-w)
    y = min(max(0, round(center[1]-h/2)), height-h)
    return x, y, w, h


def reject_pair_spikes(rows, frames):
    """Reject isolated relative-point jumps; keep raw predictions and real motion."""
    vectors=[]
    for objects in rows:
        valid=len(objects)==2 and all(o['measurement'] is not None for o in objects)
        vectors.append(tuple(objects[1]['measurement'][k]-objects[0]['measurement'][k] for k in ('x','y')) if valid else None)
    for i in range(1,len(rows)-1):
        before,current,after=vectors[i-1:i+2]
        if before is None or current is None or after is None:
            continue
        intervals=[frames[j+1]['timestampSeconds']-frames[j]['timestampSeconds'] for j in (i-1,i)]
        if not all(0 < dt <= .1 for dt in intervals):
            continue
        tolerance=max(8.,.2*min(math.hypot(*before),math.hypot(*after)))
        if (math.dist(before,after)<=tolerance*.5 and math.dist(current,before)>tolerance
                and math.dist(current,after)>tolerance):
            for obj in rows[i]:
                obj.update(measurement=None,trackingState='Lost',rejectionReason='pair-discontinuity')


def bidirectional_frames(frames, seed, max_spool_bytes=4 * 1024**3):
    """Replay a lossless prefix, including model tensors, with bounded RAM and temporary disk."""
    import tempfile
    import numpy as np
    with tempfile.TemporaryFile() as spool:
        offsets = []
        for index, image in frames:
            if seed > 0 and index <= seed:
                if spool.tell() + image.nbytes + 512 > max_spool_bytes:
                    raise ValueError('Backward tracking prefix exceeds the 4 GiB temporary disk budget; trim the video')
                # Model-ready float32 inputs are much smaller than source-resolution video frames.
                # Preserve tensor strides as well as values: inference must see the same layout on replay.
                layout = (image.device, image.stride()) if hasattr(image, 'stride') else None
                offsets.append((index, spool.tell(), layout))
                np.save(spool, image.cpu().numpy() if layout else image, allow_pickle=False)
            if index >= seed:
                yield False, index, image
        for index, offset, layout in reversed(offsets):
            spool.seek(offset)
            array = np.load(spool, allow_pickle=False)
            if layout:
                import torch
                source = torch.from_numpy(array)
                array = torch.empty_strided(source.shape, layout[1], dtype=source.dtype, device=layout[0]).copy_(source)
            yield True, index, array


def tapnext(video, pose, target, checkpoint, device, progress, resolution=256, timings=None, model=None):
    import numpy as np
    import torch
    from tapnet.tapnextpp.votsp2026.model import TAPNextPP
    from tapnet.tapnextpp.votsp2026 import utils
    started = time.perf_counter()
    if model is None:
        model = TAPNextPP.from_checkpoint(checkpoint, device=device, input_resolution=resolution)
    timings = timings if timings is not None else {}
    timings.update(modelLoadSeconds=time.perf_counter()-started, decodeWaitSeconds=0., inferenceSeconds=0.)
    state = None
    rows = [[] for _ in pose["frames"]]
    pending = []
    width, height = pose["video"]["width"], pose["video"]["height"]
    left, top, crop_width, crop_height = tracking_region(target, width, height, pose)
    query = np.array([[p['x']-left, p['y']-top] for p in target_points(target)], dtype=np.float32)
    # Official model coordinates remain 256 even with 512 input patch embeddings.
    query = utils.make_query_tensor(utils.display_to_model(query, crop_height, crop_width, 256), model.device)
    def flush():
        if not pending:
            return
        started = time.perf_counter()
        # Tracking state stays on the GPU; observations are needed only by the final result.
        batch = torch.stack([value for _, _, value in pending]).cpu().numpy()
        for (backward, index, _), values in zip(pending, batch):
            positions = utils.model_to_display(values[:, :2][:, ::-1], crop_height, crop_width, 256)
            objects = []
            for point_index, xy in enumerate(positions):
                logit = float(values[point_index, 2])
                probability = float(values[point_index, 3])
                in_crop = 0 <= xy[0] < crop_width and 0 <= xy[1] < crop_height
                objects.append(observation(target, "tapnextpp", float(xy[0])+left, float(xy[1])+top, logit > 0 and in_crop,
                    dict(visibilityLogit=logit, visibilityProbability=probability), width, height,
                    point_index if 'points' in target else None))
            if not backward or index != target["frameIndex"]:
                rows[index] = objects
        pending.clear()
        timings['inferenceSeconds'] += time.perf_counter()-started
    # Use the official wrapper's operations, retaining logits the wrapper discards.
    waiting_since = time.perf_counter()
    # Keep autocast's weight cache for the whole sequence, not just one frame.
    with torch.inference_mode(), torch.amp.autocast("cuda", dtype=torch.float16, enabled=model.device.type == "cuda"):
        backwards_started = False
        # The two recurrent passes must never share state. Original frame indices remain unchanged.
        prepared = ((i, utils.preprocess_frame(image[top:top+crop_height, left:left+crop_width], model.device, resolution))
                    for i, image in decoded_frames(video, pose))
        for backward, index, frame in bidirectional_frames(prepared, target["frameIndex"]):
            timings['decodeWaitSeconds'] += time.perf_counter()-waiting_since
            if backward and not backwards_started:
                state = None
                backwards_started = True
            inference_started = time.perf_counter()
            tracks, _, logits, state = model._model(video=frame,
                query_points=query if state is None else None, state=state)
            # Keep only a bounded batch of tiny observations, never model states or video frames.
            values = torch.cat((tracks[0, 0].float(), logits[0, 0].float(),
                                torch.sigmoid(logits[0, 0]).float()), dim=-1)
            timings['inferenceSeconds'] += time.perf_counter()-inference_started
            pending.append((backward, index, values))
            if len(pending) >= 16:
                flush()
            if index % 10 == 0:
                total = len(pose["frames"]) + (1 if target["frameIndex"] else 0)
                done = (len(pose["frames"]) - index + 1 if backward else index + 1 - target["frameIndex"])
                progress(min(1., done / total), "TAPNext++ backward tracking" if backward else "TAPNext++ forward tracking")
            waiting_since = time.perf_counter()
        flush()
    if 'points' in target:
        reject_pair_spikes(rows,pose['frames'])
    return rows


def bootstapir(video, pose, target, checkpoint, device, progress):
    import cv2
    import numpy as np
    import torch
    from tapnet.torch.tapir_model import TAPIR, FeatureGrids
    model = TAPIR(pyramid_level=1, use_casual_conv=False, feature_extractor_chunk_size=1)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
    model = model.to(device).eval()
    count = len(pose["frames"])
    width, height = pose["video"]["width"], pose["video"]["height"]
    query = torch.tensor([[[target["frameIndex"], target["point"]["y"] * 256 / height,
                            target["point"]["x"] * 256 / width]]], dtype=torch.float32, device=device)
    # Only the per-frame CNN is batched. Offline temporal refinement sees the ENTIRE
    # sequence once, preserving its actual noncausal context and queried identity.
    with torch.inference_mode():
        low = high = grids = None
        for index, image in decoded_frames(video, pose):
            rgb = cv2.cvtColor(cv2.resize(image, (256, 256), interpolation=cv2.INTER_LINEAR), cv2.COLOR_BGR2RGB)
            tensor = torch.from_numpy(np.ascontiguousarray(rgb)).to(device).float().div_(127.5).sub_(1)[None, None]
            feature = model.get_feature_grids(tensor, False, [(256, 256)])
            if low is None:
                low = torch.empty((1, count, *feature.lowres[0].shape[2:]), dtype=feature.lowres[0].dtype, device=device)
                high = torch.empty((1, count, *feature.hires[0].shape[2:]), dtype=feature.hires[0].dtype, device=device)
            low[:, index:index + 1].copy_(feature.lowres[0])
            high[:, index:index + 1].copy_(feature.hires[0])
            if index % 10 == 0:
                progress(.75 * (index + 1) / count, "BootsTAPIR offline image features")
        grids = FeatureGrids((low, low), (high, high), ((256, 256), (256, 256)))
        # Official get_query_features uses video.shape only when grids are supplied.
        shape_only = torch.empty(1, device=device).expand(1, count, 256, 256, 3)
        queries = model.get_query_features(shape_only, False, query, grids, [(256, 256)])
        progress(.8, "BootsTAPIR full-sequence offline refinement")
        trajectories = model.estimate_trajectories((256, 256), False, grids, queries, query, query_chunk_size=1)
        p = model.num_pips_iter
        predictions = {key: torch.mean(torch.stack(trajectories[key][p::p]), dim=0)[0, 0].float().cpu()
                       for key in ("tracks", "occlusion", "expected_dist")}
        visibility = (1 - torch.sigmoid(predictions["occlusion"])) * (1 - torch.sigmoid(predictions["expected_dist"]))
    rows = []
    for index in range(count):
        if index < target["frameIndex"]:
            rows.append([])
            continue
        xy = predictions["tracks"][index]
        rows.append([observation(target, "bootstapir", float(xy[0]) * width / 256,
            float(xy[1]) * height / 256, float(visibility[index]) > .5,
            dict(occlusionLogit=float(predictions["occlusion"][index]),
                 expectedDistanceLogit=float(predictions["expected_dist"][index]),
                 visibilityProbability=float(visibility[index])), width, height)])
    return rows


def run(provider, input_video, pose_json, target_json, output_json, models_root, device="cuda:0", progress=lambda p, m: None,
        tapnext_resolution=256, tapnext_checkpoint=None, model_loader=None):
    from motiontrace_ai.video_decode import validate_analysis_frames
    import torch
    start = time.perf_counter()
    pose = json.loads(Path(pose_json).read_text(encoding="utf-8-sig"))
    target = json.loads(Path(target_json).read_text(encoding="utf-8-sig"))
    validate_analysis_frames(pose)
    validate_target(pose, target)
    if 'points' in target and provider != 'tapnextpp':
        raise ValueError('The two-point workflow requires official TAPNext++')
    resolution = tapnext_resolution if provider == 'tapnextpp' else 256
    checkpoint, entry = installation(models_root, provider, resolution, tapnext_checkpoint if provider == 'tapnextpp' else None)
    if device.startswith("cuda"):
        torch.cuda.init()
        torch.cuda.reset_peak_memory_stats(device)
    tracking_timings = {}
    # Integrity validation above runs on every job, including when weights are already resident.
    model = model_loader(checkpoint, device, resolution) if provider == 'tapnextpp' and model_loader else None
    rows = tapnext(input_video, pose, target, checkpoint, device, progress, resolution, tracking_timings, model) if provider == 'tapnextpp' else bootstapir(input_video, pose, target, checkpoint, device, progress)
    if len(rows) != len(pose["frames"]):
        raise ValueError("Point tracker returned an incomplete timeline")
    if 'points' in target and any(len(objects) != 2 for objects in rows):
        raise ValueError('TAPNext++ must return both queried points across the full bidirectional timeline')
    result = copy.deepcopy(pose)
    result.update(schemaVersion=4, provider=provider, target=target)
    for frame, objects in zip(result["frames"], rows):
        frame["shaft"] = None
        frame["shafts"] = []
        frame["objects"] = objects
    checkpoint_name, checkpoint_hash, checkpoint_size = TAPNEXT_CHECKPOINTS[resolution] if provider == 'tapnextpp' else CHECKPOINTS[provider]
    result["trackingModel"] = dict(entry, repositoryRevision=REVISION, adapterVersion=VERSION,
        checkpoint=checkpoint_name, checkpointPath=str(checkpoint),
        files=[dict(path=checkpoint_name, sha256=checkpoint_hash, size=checkpoint_size)],
        checkpointSha256=checkpoint_hash, resolution=[resolution, resolution],
        mode="bidirectional-recurrent" if provider == "tapnextpp" else "offline-full-sequence",
        preprocessing="RGB [-1,1], stretch resize, xy output pixels; query tyx model pixels",
        precision="float32 weights, float16 CUDA autocast" if provider == "tapnextpp" else "float32",
        queryFrame=target["frameIndex"], measurementMethod="user-queried-physical-point",
        qualityPolicy="visible in bounds: Reduced; model confidence is not calibrated measurement accuracy")
    if provider == 'tapnextpp':
        result['trackingModel']['sourceRegionXYWH'] = list(tracking_region(target, pose['video']['width'], pose['video']['height'], pose))
        result['trackingModel']['coordinateResolution'] = [256, 256]
    result["performance"] = dict(elapsedSeconds=time.perf_counter() - start,
        peakGpuAllocatedBytes=torch.cuda.max_memory_allocated(device) if device.startswith("cuda") else 0)
    if tracking_timings:
        result['performance']['trackingTimings'] = tracking_timings
    result["versions"] = dict(pose["versions"], barbellProvider=provider,
        barbellModelVersion=result['trackingModel']['checkpointSha256'], measurementVersion=VERSION)
    result["athletes"] = [dict(a, isExerciseParticipant=a["id"] == target["athleteTrackId"])
                          for a in pose["athletes"]]
    result["visionMetadata"] = dict(provider=provider, target=target,
        trackingModel=result["trackingModel"], performance=result["performance"],
        measurementMethod="user-queried-physical-point", isProxy=False)
    path = Path(output_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    progress(1., "Point tracking complete")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=tuple(CHECKPOINTS), required=True)
    for argument in ("input", "pose-input", "target", "output", "models-root"):
        parser.add_argument("--" + argument, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument('--tapnext-resolution', type=int, choices=(256,512), default=256)
    parser.add_argument('--tapnext-checkpoint', default=None)
    args = parser.parse_args()
    def report(value, message):
        print(json.dumps(dict(type="progress", value=value, progress=value, message=message)), flush=True)
    run(args.provider, args.input, args.pose_input, args.target, args.output, args.models_root, args.device, report,
        args.tapnext_resolution, args.tapnext_checkpoint)
