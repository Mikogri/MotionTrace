# Real comparison session probe

This executable calls production `ComparisonAnalysisEngine.AnalyzeAsync` once
without a provider filter, then restores the persisted prepared snapshots through
`TryRestoreAsync`. It uses explicit interpreters and model directories. GPU work
must be coordinated with other analyses on the same computer.

Build with the same configuration/platform as the app because the production
snapshot identity includes the Core and Infrastructure module IDs:

```powershell
dotnet build research/comparison/SessionProbe/SessionProbe.csproj -c Release -p:Platform=x64
dotnet research/comparison/SessionProbe/bin/x64/Release/net10.0/SessionProbe.dll --analyze C:/Work/Projects/MotionTrace 'C:/Work/Projects/MotionTrace/videos/bench/100kg x 5.mp4' C:/Work/Projects/MotionTrace/artifacts/four-trackers/bench-target.json C:/Work/Projects/MotionTrace/artifacts/four-trackers/full-session
```

Use `--restore-only` to reopen existing results without calling Analyze. Keep
target bytes and production code unchanged during a run: they are cache identity
inputs. Model/source integrity errors remain explicit provider failures.

The report contains the status, classification, trajectory sample count, rep/phase
data, prepared chart counts, restore duration and 1000 warm selection timings.
Timing covers `AnalysisSession.Activate` and reading precomputed data references;
it does **not** measure WinUI binding, mask loading, overlay drawing, video seeking
or playback smoothness. A separate rendered UI test is needed for those claims.

Exit 0 requires all four providers Ready both before and after restore. Failure
still writes the report so successful providers and diagnostic details survive.

## Recorded run, 2026-09-22

The command above completed with exit 0. All four providers produced 565 frames,
565 physical-point trajectory samples for athlete 2 and five independently computed
Bench Press reps with phases. Athlete 1 had no barbell trajectory/reps. The shared
X-CLIP decision was BenchPress for athlete 2 and Unknown for athlete 1. This is a
development-video functional check, not an independent positional-accuracy result.

- One Analyze call: 499.145 seconds (the shared pose cache was warm).
- Prepared disk restore in the same process: 1.257 seconds.
- Separate-process `--restore-only`: all four Ready in 1.870 seconds, zero Analyze
  events; repeat restore 1.216 seconds.
- 1000 warm lightweight reference switches: median 0.0011 ms, p95 0.0016 ms,
  maximum 13.9293 ms. These numbers do not describe rendered WinUI performance.
- The actual scheduler ran the four jobs sequentially under current memory
  pressure on the 8 GiB GPU / 16 GiB RAM computer. No model or resolution was changed.
- A five-second resource sampler, started during SAMURAI and continuing through
  both point trackers, observed total GPU usage up to 3482 MiB including desktop.
  Maximum sampled Python process peak working set was 4123.36 MiB. Sampling does
  not prove the absolute peak across the entire session.

Evidence: `artifacts/four-trackers/full-session/probe-report.json`,
`restore-report.json`, `artifacts/four-trackers/full-session-probe.log`, and
`full-session-resources.jsonl`. One earlier probe was deliberately interrupted
before any Ready result to incorporate the point-only export fix; its log is
separate and its partial files were not counted as completed results.
