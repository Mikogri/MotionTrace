# Conservative exercise recovery

`ExerciseResolver.Resolve(AnalysisResult, athleteId)` preserves any accepted known video-model exercise decision for confirmed exercise participants, including Olympic lifts that must not be reinterpreted as deadlift. When that decision is Unknown or absent, it evaluates assigned bar movement together with visible shoulder/hip/wrist anatomy. Background people and unassigned or stationary bars cannot establish an exercise.

The fallback requires a complete movement candidate, sufficient visible anatomy, meaningful bar and wrist travel, positive bar/wrist motion correlation, and a unique supported exercise. Squat requires the bar near shoulder height and an upright torso; deadlift requires hanging arms/bar near or below hip level; bench requires a reclining torso and elevated hands. Existing conservative bench rules can also contribute when overlapping a complete owned-bar repetition. Conflicting candidates remain Unknown.

For mask proxies, the point is not a validated shaft axis: anatomical height therefore comes from visible wrists. Proxy movement must still correlate with their motion. Deadlift anatomy/correlation is evaluated during the pull, because letting go after lowering is not evidence against a correctly identified lift. No model weights, confidence of hidden joints, or movement thresholds were changed by this resolver.

The returned `ExerciseClassification.Limitation` records model method or `owned-bar-anatomy-1` fallback provenance. Its confidence is evidence strength, not calibrated probability. It cannot recover an exercise when the bar, complete motion, or body evidence is missing. Manual selection remains available.

## Saved-data evaluation

CPU replay used the six existing annotated videos and saved generic/custom outputs from `artifacts/model-comparison`, without new GPU inference. Reproducible command: run `research/barbell/ExerciseProbe` with analysis JSON paths; the probe does not modify inputs. The final probe applies `TemporalPoseCorrector(new(), new LightPoseSmoother())`, matching the application, and computes the legacy six-second bench windows every half-second for schema 3. Final results: `artifacts/model-switch-repair/exercise-recovery-corrected.json`; the earlier raw-only diagnostic remains at `artifacts/model-switch-repair/exercise-recovery.json`.

Generic outputs preserve both bench and both squat labels, and now recover the first deadlift previously Unknown: **5/6 expected video labels**, versus 4/6 before recovery. The second deadlift has no confirmed owner/bar and remains Unknown (no participant row in the report). This is classification evidence only, not a claim that every repetition or phase was recovered.

On the saved custom outputs, the fallback recognizes the first deadlift. Several other videos lack a complete bar cycle or sufficiently visible hips; they deliberately remain Unknown in this resolver. The existing legacy bench classifier remains available separately in the UI, but it also returns Unknown on these saved bench examples. The fresh `artifacts/model-switch-repair/bench-production.json` similarly remains Unknown after correction and legacy classification and requires manual BenchPress selection. No broad custom-classification improvement is claimed.

These recordings are a development/regression set, not independent validation. Thirteen focused .NET tests cover all three positive exercise cases, stationary bar/person, unassigned bar, excluded spotter, bench unrack, accepted model preservation including Olympic lifts, proxy offset, and conflicting movements.
