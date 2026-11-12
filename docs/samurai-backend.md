# SAMURAI adapter

This is the official modified `sam2` implementation from
https://github.com/yangchris11/samurai at revision
`76ba195984892b0d1e3db5d9c9f90bb62175680a`, not the Transformers SAM2 wrapper.
Configuration: `configs/samurai/sam2.1_hiera_s.yaml`, `samurai_mode: true`.
Checkpoint: official Meta SAM 2.1 small,
`https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt`,
SHA256 `6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38`.

## Installation and isolation

Run `scripts/setup-samurai.ps1`. The dedicated `motiontrace-samurai` environment
uses Python 3.11.16, PyTorch 2.8.0+cu126, torchvision 0.23.0+cu126. Exact dependency
versions are in `scripts/requirements-samurai.lock.txt`. Neither the MMPose nor
existing Transformers vision environment is modified. Local source and checkpoint
are in `.models/samurai`; `manifest.json` records their hashes and interpreter.
Inference checks source/checkpoint integrity and uses only local paths.

The optional SAM2 connected-component CUDA extension is not built on Windows.
The adapter explicitly disables optional automatic mask postprocessing (including
hole filling); it retains all configured SAMURAI Kalman, motion-score and
memory-selection behavior. This choice is recorded in the output configuration.
The upstream source remains unmodified.

Code and SAM2.1 checkpoint are Apache-2.0. The cloned source retains the root
LICENSE, SAM2 LICENSE and LICENSE_cctorch (third-party component notice). The
pinned upstream tree does not contain a root NOTICE file. No benchmark dataset or
demo movie is downloaded. The sparse checkout includes the upstream SAM2 package
and scripts, with their original license headers.

## Adapter contract

```
motiontrace-samurai/python.exe ai/comparison/samurai_backend.py \
  --input video.mp4 --pose-input shared-pose.json --target target.json \
  --output samurai.json --models-root .models/samurai --device cuda:0
```

Target is the common physical-point initialization (`targetId`, `athleteTrackId`,
`frameIndex`, `timestampSeconds`, original-pixel `box` and `point`, calibration).
The box is passed as XYXY to the official predictor; the user point is **not** a
mask centroid. Existing `vision.measurement.MeasurementPoint` tracks that point
with forward/backward-validated LK inside the independent SAMURAI mask. Loss is
missing measurement; it never becomes a zero coordinate or centroid fallback.
Quality is Reduced, method `manual-lk`, `isProxy=false`, no interpolation.
This point extraction is MotionTrace logic, not a point output natively produced
by SAMURAI and not a TAPNext++/BootsTAPIR trajectory.

Output preserves all shared pose frames/timestamps/exercise predictions in schema4
and removes shaft measurements from other providers. Frames before the query have
empty objects. Raw mask, mask box, mask affinity, object-score logit and Kalman score
are indexed separately in `.raw.json` and `.masks/*.png`; object measurement is the
mask-constrained physical point. C# owns subsequent smoothing, velocity and reps.

## Temporal state and bounded storage

The official eager video loader would allocate all 1024x1024 float frames. Only
that loader is replaced by a one-frame PyAV/Pillow adapter using the existing
MotionTrace rotated-frame decoder and real PTS. RGB, resize, ImageNet normalization
and original-pixel mask coordinates are explicit. Every decoded timestamp and EOF
must match the shared timeline; truncated or extra frames fail without Ready.

One continuous official predictor processes the whole query-to-EOF sequence.
Kalman state and initial conditioning frame are retained. Heavy tensors retain the
last 15 eligible SAMURAI memories plus the last 16 pointer frames; all lightweight
score history remains for the official backward scan. This preserves the exact
future memory-selection inputs; it does not reset or truncate tracking into clips.
Video offset is handled outside the predictor so a nonzero query maps to internal
frame0 while preserving every original output timestamp. Reverse tracking is not
performed and is recorded as `forward-temporal`.

## Verification

Focused tests cover target/frame matching, physical point validation, retained
memory eligibility across long occlusion, and preservation of the official score
scan after tensor eviction. GPU run results are recorded separately after real
inference; installation/import alone is not a tracking-quality test.

Real GPU test (2026-09-22): `videos/bench/100kg x 5.mp4`, shared pose
`artifacts/model-switch-repair/bench-production.json`, manual near plate-hub axis
point `(613,1576)` at frame0, common box `(190,1325,1900,525)`.
`artifacts/four-trackers/samurai-bench.json` has all 565 frames and 565 observed
mask-constrained physical-point measurements; original PTS are retained. Runtime
161.25 seconds, PyTorch peak allocated GPU memory 736,394,752 bytes. Sampled process
peak working set 2009 MiB; total device usage (including desktop) was 2341 MiB.
These are different resource measures and should not be compared as equivalent.
Masks at frame0 and frame250 were visually inspected: bar and plates were segmented,
including hand occlusion. A correct-looking mask is not independent position ground
truth. Shared existing C# `AnalysisProbe` successfully parsed the schema and produced
per-athlete physical-point trajectories and phases; output is
`artifacts/four-trackers/samurai-bench-metrics.json`.
Five focused Python tests pass (`artifacts/four-trackers/samurai-tests.log`).
