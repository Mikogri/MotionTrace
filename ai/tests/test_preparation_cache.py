import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparison import prepare
from vision.cache import file_digest


class PreparationCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'video.mp4').write_bytes(b'video')
        pose = dict(schemaVersion=3, video=dict(width=640, height=480, framesPerSecond=25, durationSeconds=.12),
                    athletes=[dict(id=2), dict(id=3)],
                    frames=[dict(timestampSeconds=i*.04, athletes=[], shafts=[]) for i in range(3)])
        (self.root/'pose.json').write_text(json.dumps(pose))
        self.target = dict(athleteTrackId=2, timestampSeconds=0, points=[dict(x=100,y=200),dict(x=400,y=200)])
        (self.root/'target.json').write_text(json.dumps(self.target))
        weights = self.root/'models/xclip/weights.bin'
        weights.parent.mkdir(parents=True)
        weights.write_bytes(b'weights')
        self.manifest = dict(models=dict(xclip=dict(revision='test', files=[dict(path='weights.bin',
                             size=weights.stat().st_size, sha256=file_digest(weights))])))
        (self.root/'models/manifest.json').write_text(json.dumps(self.manifest))
        self.args = SimpleNamespace(input=str(self.root/'video.mp4'), pose_input=str(self.root/'pose.json'),
                                    target=str(self.root/'target.json'), models_root=str(self.root/'models'),
                                    resolved_target=str(self.root/'resolved.json'), output=str(self.root/'out.json'),
                                    cache=str(self.root/'cache'), device='cpu')

    def tearDown(self):
        self.temp.cleanup()

    def test_changed_points_reuse_predictions_but_changed_owner_reruns(self):
        with patch('vision.pipeline.classify_exercises', return_value=[dict(athleteId=2, exercise='BenchPress')]) as classify:
            prepare.run(self.args)
            first = json.loads(Path(self.args.output).read_text())['exercisePredictions']
            self.target['points'][0]['x'] += 20
            Path(self.args.target).write_text(json.dumps(self.target))
            prepare.run(self.args)
            self.assertEqual(1, classify.call_count)
            self.assertEqual(first, json.loads(Path(self.args.output).read_text())['exercisePredictions'])
            self.assertEqual(self.target['points'], json.loads(Path(self.args.resolved_target).read_text())['points'])
            self.target['athleteTrackId'] = 3
            Path(self.args.target).write_text(json.dumps(self.target))
            prepare.run(self.args)
            self.assertEqual(2, classify.call_count)

    def test_cache_does_not_bypass_checkpoint_integrity(self):
        with patch('vision.pipeline.classify_exercises', return_value=[]) as classify:
            prepare.run(self.args)
            (self.root/'models/xclip/weights.bin').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Corrupted or modified'):
                prepare.run(self.args)
            self.assertEqual(1, classify.call_count)

    def test_identity_invalidates_video_pose_device_weights_and_sources(self):
        source = self.root/'sources'
        for name in ('comparison/prepare.py', 'vision/pipeline.py', 'motiontrace_ai/video_decode.py'):
            path = source/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('source')
        def key():
            return prepare.classification_key(self.args, 2, self.manifest, source)
        previous = key()
        for path in (Path(self.args.input), Path(self.args.pose_input), source/'vision/pipeline.py'):
            path.write_bytes(path.read_bytes()+b' ')
            current = key()
            self.assertNotEqual(previous, current)
            previous = current
        self.args.device = 'cuda:0'
        current = key()
        self.assertNotEqual(previous, current)
        self.manifest['models']['xclip']['files'][0]['sha256'] = 'new checkpoint hash'
        self.assertNotEqual(current, key())

    def test_corrupt_or_stale_predictions_recompute_including_empty_results(self):
        path = self.root/'cache.json'
        calls = []
        def classify():
            calls.append(1)
            return []
        self.assertEqual([], prepare.cached_classification(path, 'key', classify))
        self.assertEqual([], prepare.cached_classification(path, 'key', classify))
        self.assertEqual(1, len(calls))
        content = json.loads(path.read_text())
        content['predictions'] = [dict(exercise='Squat')]
        path.write_text(json.dumps(content))
        self.assertEqual([], prepare.cached_classification(path, 'key', classify))
        self.assertEqual(2, len(calls))
        path.write_text('{truncated')
        prepare.cached_classification(path, 'key', classify)
        prepare.cached_classification(path, 'new-key', classify)
        self.assertEqual(4, len(calls))


if __name__ == '__main__':
    unittest.main()
