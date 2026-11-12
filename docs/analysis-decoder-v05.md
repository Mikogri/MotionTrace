# Analysis and playback fixes — engine 0.5

The user log showed two failures: OpenCV reported a -0.001667 s first timestamp for IMG_0808.MOV, rejected by the C# schema; IMG_0432.MOV had 627 declared samples but only 620 presentation frames, causing the old count-based EOF check to fail.

The engine now uses PyAV 16.1.0 presentation timestamps and decoded frames, including the MOV display rotation. It does not require decoded frame count to equal the sample table. Missing/non-monotonic timestamps, corrupt frames, dimension changes and material early end relative to stream duration still fail; tiny negative leading timestamps covering time zero are clamped. Source videos are unchanged. PyAV's decoder returned 620 complete presentation frames for IMG_0432 and 1329 nonnegative-timestamp frames for IMG_0808.

People in each frame are now sent through RTMPose together instead of one GPU call per person. Torch uses four CPU threads, OpenCV two and the decoder four. Every video frame and the existing pose model are retained. Model, decoder package and adapter hashes participate in cache identity, so old failing results are not reused. Error UI now shows the final Python exception cause; the complete traceback remains in the application log.

Playback adds a 0–100% volume slider, percentage display and mute button. Unmuting a zero-volume slider restores its last audible value. These control the local MediaPlayer, not system volume. The control row and portrait column height budget were adjusted to fit it.

## Verification

- 23 Python and 73 .NET tests pass; build and self-contained publish to `artifacts/app` succeeded.
- Full IMG_0432 analysis: 620 frames, successful C# JSON parsing and pose correction (`artifacts/shaft_model/fixed-0432-probe.json`).
- Full IMG_0808 analysis: 1329 frames, successful decoding and C# JSON parsing/correction (`artifacts/analysis-performance/0808-probe.json`).
- Same local eight-second, 240-frame benchmark, sequential runs without cached results: previous engine 40.99 s; new engine 34.73 s (15.3% less elapsed time). Results are in `artifacts/analysis-performance/comparison.json`; this one-machine measurement is not a guarantee for every video. Full IMG_0808 took 165.28 s.
- Native UI inspection confirmed the visible volume controls, mute state and slider changing to 50%.

Decoder references: [PyAV stream timing](https://pyav.org/docs/stable/api/stream.html), [decode and EOF flushing](https://pyav.org/docs/develop/api/container.html), [frame rotation implementation](https://github.com/PyAV-Org/PyAV/blob/main/av/video/frame.py).
