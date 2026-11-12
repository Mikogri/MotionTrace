# Measurement source and continuity fixes

Verified against cached engine 0.5 outputs for `VID_20260424_214030~2.mp4` (606 frames) and `IMG_0809.MOV` (1560 frames), without changing videos or annotations.

The MP4 had shaft observations on all frames but its only original corrected-wrist candidate was rejected by the per-frame ownership gate. A shaft track ID also changed near the bottom of the lift when the visible fragments changed. Treating that as an entirely new trajectory lost the full rep.

Changes:

- Measurement source selects Wrist or Barbell. Barbell follows the detected shaft independently of wrist/athlete selection; wrist retains athlete and side selection.
- Shaft displacement compares overlapping visible fragments at the same X. Adding/removing fragments cannot move a centroid and create a false displacement. Short reacquisition of geometrically matching fragments can retain continuity; long gaps or incompatible ownership split it. Optical-flow displacement is only a fallback when no fragment overlap remains on the same track. This remains an image-space estimate, not calibrated m/s; camera movement and detection errors can affect it.
- At most three low-confidence samples within a 0.15 s bracket can be interpolated between valid, nearby points, with reduced quality. Long gaps are not filled. Global pose quality alone no longer rejects an otherwise valid wrist sample.
- Shaft confirmation allows temporarily unknown ownership on a continuous moving track, but still requires two ownership observations and rejects another athlete's assignment. Stationary shaft tests remain negative.
- The lowering start is refined to the latest quiet interval before the clear drop, avoiding old extrema during setup. Existing incomplete-rep, pause, deadlift and immediate-next-rep checks still pass.
- All complete reps are initially selected for comparison. With no complete rep, Time mode shows the available continuous trajectory, rather than a blank chart. Source-specific captions/metrics identify Wrist or Barbell.
- No text label is drawn above the shaft. Playback volume is a button at the right of the seek row; clicking opens a slider/mute flyout.

Recorded barbell-mode results (development checks, not independent accuracy):

| Video | Rep interval | Lowering | Lifting |
| --- | --- | --- | --- |
| VID_20260424_214030~2.mp4 | 6.442–10.192 s | 1.790 s | 1.723 s |
| IMG_0809.MOV | 39.902–41.035 s | 0.600 s | 0.400 s |
| IMG_0809.MOV | 41.135–42.068 s | 0.367 s | 0.500 s |

Results and trajectories: `artifacts/shaft_model/measurement-mp4.json`, `measurement-0809.json`, and `reported-*.json.shaft-points.json`. The motion threshold remains user-configurable. Wrong person selection, longer occlusion, genuinely incomplete footage or false shaft detections can still omit/misidentify a rep.

79 .NET tests passed. Release publish succeeded to `artifacts/app-measurement` because the running older app locked the normal destination. Native UI inspection confirmed source selection control and the volume flyout.
