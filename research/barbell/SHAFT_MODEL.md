# Shaft detection v1

Implemented on 2026-09-13. The review page, its storage, source videos and original annotation export were not changed.

## Training and evaluation

`training_annotations.json` supplies 300 user-reviewed frames, 720 visible line segments, 134 notes. The 91 reviewed-but-edited records were approved at the user's request; occluded-with-lines was normalized to partial in a separate export. Annotation coordinates and notes were preserved.

The visible shaft center lines become 3-pixel-wide training masks on a 512-square letterboxed image. No labels for plates or sleeves are generated. A ResNet18 encoder initialized with ImageNet weights and a small segmentation decoder learn these masks. The decoder is trained from scratch. Random flip, rotation, translation, scale, brightness and contrast augment the training images. No media is uploaded. Initialization uses the official [torchvision ResNet18 weights](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.resnet18.html); inference needs only the local checkpoint.

Split is by the existing provisional visual families, not random neighboring frames:

| Split | Frames | Family |
| --- | ---: | --- |
| Train | 226 | All remaining families |
| Validation | 50 | front_ceiling_rack |
| Development test | 24 | low_window_20251014 |

30 epochs, seed 42, AdamW 0.0003, batch 6, weighted BCE + Dice loss, RTX 3070 Ti. Best checkpoint selected by validation mask F1 at epoch 29. Fixed inference threshold 0.5.

Validation mask F1: 0.8435. Development test mask F1: 0.7968. With a three-pixel tolerance on the 512 image, mask precision/recall are 0.9809/0.9786 (validation) and 0.9916/0.9339 (test). All 74 held-family frames yielded extracted line segments. These are pixel localization scores, NOT repetition accuracy or a claim that every detected segment is correct. The contact sheet was visually inspected. Families are provisional and are not verified capture sessions; a new independent session is still needed for final evaluation. There is only one absent-bar annotation, so absent-bar false-positive performance is not established.

Outputs: `artifacts/shaft_model/best.pt`, `split.json`, `history.json`, `evaluation.json`, `evaluation.jpg`. Deployed checkpoint: `ai/models/shaft-v1.pt`. SHA256 of the annotation input is embedded in the checkpoint.

## Runtime

`shaft_model.py` extracts thin, approximately straight components from the probability mask, mapping them back to original frame coordinates. `shaft_tracking.py` detects at least every 0.1 s and uses forward/backward Lucas–Kanade flow between detections. Robust background flow outside previous person boxes and the shaft compensates camera translation. Missing features, ambiguous detections, long gaps and detector reacquisition do not produce reliable displacement. Flow is an image-space estimate; rotation, zoom, occlusion and texture changes remain limitations.

Ownership requires confident wrists near the detected segments. One visible wrist is accepted only at higher confidence (0.6) and a tighter distance (2.5% of frame height, versus 4.5% with both wrists). For this bench-only model, wrists below the shoulders are excluded as a standing-spotter cue; competing similar candidates remain unassigned. This does not implement learned ReID or permanent identity across leaving and re-entering the scene.

Python emits a nullable `shaft` observation per frame with fragments, track ID, optional athlete ID, confidence, reliable-flow flag and camera-compensated delta Y/time. DTO validation rejects invalid coordinates and metadata; temporal pose correction preserves shaft observations. The model hash and adapter source hashes invalidate old inference caches.

The WinUI overlay draws shaft fragments cyan when flow is available and gold when only localized. The label shows ownership or uncertainty. For bench press with a shaft model, `ShaftRepGate` retains a wrist repetition only when at least three continuous observations of one shaft track and athlete show upward net travel of 0.4% of image height over at least 0.12 s inside the lifting phase. Unconfirmed candidates are counted in the note but excluded from the rep list. Wrist timing and px/s remain unchanged. This gate can miss real reps when wrist candidates or shaft evidence are unavailable. Squat/deadlift retain the previous wrist behavior; this dataset does not validate shaft gating for them.

## Reproduce

Run from the project root in the motiontrace Python environment:

```powershell
python research/barbell/train_shaft.py --epochs 30 --batch 6
python research/barbell/evaluate_shaft.py
Copy-Item artifacts/shaft_model/best.pt ai/models/shaft-v1.pt
$env:PYTHONPATH='ai'
python -m unittest discover -s ai/tests
dotnet test tests/MotionTrace.Tests/MotionTrace.Tests.csproj
```

`AnalysisProbe` reads real engine JSON through the C# adapter, applies pose correction, compares wrist candidates with shaft-confirmed reps, and reports coverage. Example:

```powershell
dotnet run --project research/barbell/AnalysisProbe -- artifacts/shaft_model/bench-front.json
```

Re-run Analyze video in the newly published app to obtain shaft observations. Existing analyses loaded into an already running app do not acquire these fields retroactively.

## Integration checks

73 .NET tests and 18 Python tests pass. Release self-contained WinUI publish completed to `artifacts/app`; deployed model and tracker hashes match their source copies.

Two eight-second local clips were analyzed with the full RTMDet/RTMPose/shaft pipeline; the final ownership change was replayed over the same poses and frames. Real JSON was parsed and corrected by `AnalysisProbe`:

- IMG_0789 excerpt: 240/240 frames localized, 239 with flow, 218 assigned; athlete 2 left-wrist candidate at 1.2–5.4 s confirmed. Other wrist/spotter yielded no candidates.
- 100kg x 5 excerpt: 240/240 localized, 236 with flow, 106 assigned. The existing corrected-wrist analyzer produced no complete candidates (the raw right-wrist signal had two). Shaft tracking cannot restore candidates lost to pose quality/correction. This is an unresolved limitation, not a successful repetition-count test.

`probe_learned_shaft.py` checks nine previously reviewed 0.8-second development windows without supplying manual localization. Five stationary labels remained stationary; three of four moving labels were detected. The dark IMG_7845 window was predicted stationary (1.93 px range versus 2.56 px threshold at 640-pixel height). No thresholds were adjusted after this check. These small, source-overlapping windows are not independent detector or repetition accuracy estimates.
