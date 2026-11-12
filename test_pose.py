from mmpose.apis import MMPoseInferencer

inferencer = MMPoseInferencer(
    pose2d="human",
    device="cuda:0"
)

results = inferencer(
    "bench_reel.mp4",
    out_dir="output"
)

for _ in results:
    pass

print("Gotowe")