"""Create a local no-lift validation excerpt; leave the source video untouched."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

import av

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai"))
from motiontrace_ai.video_decode import VideoDecoder

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--end", required=True, type=float)
args = parser.parse_args()
target = Path(args.output)
target.parent.mkdir(parents=True, exist_ok=True)
decoder = VideoDecoder(args.input)
timestamps = []
try:
    with av.open(str(target), "w") as container:
        stream = container.add_stream("libx264", rate=Fraction(decoder.fps).limit_denominator(100000))
        stream.width, stream.height = decoder.width, decoder.height
        stream.pix_fmt = "yuv420p"
        stream.time_base = stream.codec_context.time_base = Fraction(1, 90000)
        stream.options = {"crf": "18", "preset": "fast"}
        for timestamp, image in decoder:
            if timestamp >= args.end:
                break
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            frame.pts, frame.time_base = round(timestamp * 90000), Fraction(1, 90000)
            timestamps.append(timestamp)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
finally:
    decoder.close()
target.with_suffix(".source.json").write_text(json.dumps(dict(
    source=str(Path(args.input).resolve()), requestedEnd=args.end,
    sourceTimestamps=timestamps, note="Re-encoded validation excerpt, original dimensions; no audio.")), encoding="utf-8")
print(f"Saved {len(timestamps)} frames to {target}")
