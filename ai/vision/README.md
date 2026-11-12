# Offline vision stage

Run with the **motiontrace-vision** interpreter. This package deliberately has no
import of the custom shaft detector, its weights or MMPose. The parent pipeline
supplies preserved RTMPose observations through `--pose-input`.

```powershell
& "$env:USERPROFILE/miniconda3/envs/motiontrace-vision/python.exe" ai/vision/analyze.py `
  --input videos/example.mp4 --pose-input artifacts/example.pose.json `
  --output artifacts/example.vision.json --cache artifacts/vision-cache `
  --models-root "$env:LOCALAPPDATA/MotionTrace/models/vision" --device cuda:0
```

The installed manifest and weights are prepared by `scripts/setup-vision.ps1`.
Inference forces offline mode and local model paths; missing files fail without
network access or fallback. Standard output contains JSONL progress. Model
diagnostics go to standard error.

## Stages and memory

1. Grounding DINO detects candidates every 2 seconds. Geometry and temporal
   agreement with wrist/shoulder motion associate them with existing tracked
   people. At least three moving observations are required; ambiguous or static
   cases remain unassigned. Initialization waits until that person is visible.
2. SAM 2 Video processes every source frame, initialized at an accepted candidate
   or correction timestamp. Models are not simultaneously resident. SAM temporal
  state is offloaded to CPU; complete recent memory/pointer receptive fields are
   kept together with original/latest conditioning anchors. Full-video pixels are
   not retained. Masks are losslessly stored as separate PNG artifacts. A mask
   covering at least 75% of the central torso polygon (all four shoulder/hip
   joints confident) is rejected as a possible person segmentation. The object
   becomes Lost with null measurement until a new detection/manual prompt;
   rejection counts and policy thresholds are persisted in vision metadata.
3. X-CLIP classifies moving person-context crops using the checkpoint's frame
   count, preprocessing and temporal samples mapped to source presentation times.
   Four-second windows include explicit non-lift prompts. Raw prompt logits,
   class-mean logits and per-window decisions are persisted. Final decisions
   aggregate accepted windows with agreement and score/margin checks. These
   scores are **not calibrated probabilities**. Tracks without verified object
   ownership are finally marked Unknown; their raw X-CLIP `modelExercise`, scores
   and windows are retained separately from this explicit ownership gate.

Detection thresholds, prompts and sampling policy are in `config.py` and form
part of the cache identity. The CLI verifies every installed manifest file's
size and SHA-256 before inference; the manifest contains checkpoint revisions.
This stage writes results and artifacts but currently does not shortcut through
a full-result cache. Pose-stage cache reuse remains the parent's responsibility.

## Corrections

Optional `--corrections corrections.json`:

```json
{
  "videoHash": "SHA256_OF_ORIGINAL_VIDEO",
  "objects": [
    {
      "objectId": "bar-1",
      "athleteId": 1,
      "timestampSeconds": 3.5,
      "box": [100, 200, 400, 300],
      "point": [160, 245]
    }
  ]
}
```

Box and point may be used separately or together. All coordinates refer to the
rotation-corrected original video. Repeated entries for the same object update
its prompt at the nearest real presentation timestamp. The object remains bound
to one person. A new correction invalidates the result key and deterministically
reprocesses the clip; partial replay optimization is not implemented.

Automatic measurements are labelled `mask-proxy`: center of mask extent, not the
bar axis. A manually selected point uses forward/backward checked Lucas–Kanade
flow and mask membership. A lost manual point produces null, never a substitute
mask center. No velocity, repetition or phase algorithm is duplicated here.

## Known limitations

- Geometry and conservative continuity are useful gates, not proof of ownership.
  Spotters or two nearby bars may require manual selection.
- Short occlusion can recover using temporal memory and matching geometry/
  appearance. After longer ambiguous loss, the output remains Lost until a safe
  candidate or manual correction; no arbitrary highest-score switch occurs.
- General-purpose segmentation may track a plate, the full barbell or another
  prompted region. Proxy movement is explicitly not validated bar-axis motion.
- X-CLIP uses context crops, not person-instance masks. Nearby activity may still
  influence the result. Thresholds need validation on labelled local videos.
- This backend proposes Snatch/CleanAndJerk but does not implement their reps,
  phases, RPE or calibration. Those are presentation/analytics responsibilities.

Run `python -m unittest vision.test_vision` with `PYTHONPATH=ai` for policy tests.
`smoke.py --models-root ... --video ... --output ...` executes all three actual
checkpoints offline and SAM across consecutive frames. A smoke pass is an
execution check, not an accuracy benchmark.
