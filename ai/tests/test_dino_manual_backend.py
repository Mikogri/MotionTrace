"""The comparison backend consumes the shared manual prompt without another detection pass."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from comparison.dino_backend import run


class DinoManualBackendTests(unittest.TestCase):
    def test_uses_shared_target_and_skips_unused_full_video_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pose = dict(frames=[dict(timestampSeconds=0, athletes=[])],
                        athletes=[dict(id=1), dict(id=2)], versions={})
            target = dict(frameIndex=0, athleteTrackId=2, targetId="physical-bar",
                          box=dict(x=10, y=20, width=40, height=10), point=dict(x=30, y=25))
            for name, value in (("pose.json", pose), ("target.json", target), ("manifest.json", {})):
                (root/name).write_text(json.dumps(value))
            args = SimpleNamespace(input="video.mov", pose_input=str(root/"pose.json"),
                                   target=str(root/"target.json"), output=str(root/"output.json"),
                                   models_root=str(root), device="cpu")
            with patch("vision.pipeline.verify_manifest"), \
                 patch("vision.pipeline.detect_candidates", side_effect=AssertionError("Redundant detection")), \
                 patch("vision.pipeline.track_objects", return_value=[[]]) as tracking, \
                 patch("torch.cuda.max_memory_allocated", return_value=0):
                run(args)
            self.assertEqual({}, tracking.call_args.args[2])
            prompt = tracking.call_args.args[3][0][0]
            self.assertEqual("physical-bar", prompt["objectId"])
            self.assertEqual(2, prompt["athleteId"])
            self.assertEqual([30, 25], prompt["point"])
            self.assertEqual([10, 20, 50, 30], prompt["box"])
            output = json.loads((root/"output.json").read_text())
            self.assertEqual([False, True], [a["isExerciseParticipant"] for a in output["athletes"]])
            self.assertEqual("grounding_dino_sam2", output["versions"]["barbellProvider"])


if __name__ == "__main__":
    unittest.main()
