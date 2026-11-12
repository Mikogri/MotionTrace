import copy
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from vision.classify_custom import owned_shaft_objects, classify_result, load_predictions, save_predictions
from pipeline import analyze, custom_classifier_available


class CustomClassificationTests(unittest.TestCase):
    def sample(self):
        segment = dict(x1=10, y1=20, x2=50, y2=20)
        shafts = [dict(athleteId=i, segments=[segment], ownershipAmbiguous=ambiguous)
                  for i, ambiguous in ((1, False), (2, False), (None, False), (1, True))]
        return dict(schemaVersion=3, provider='custom_barbell', frames=[dict(timestampSeconds=0, athletes=[], shafts=shafts)],
                    athletes=[dict(id=1, isExerciseParticipant=True), dict(id=2, isExerciseParticipant=False)])

    def test_only_confirmed_owned_unambiguous_shafts_are_classifier_context(self):
        objects = owned_shaft_objects(self.sample())
        self.assertEqual(1, len(objects[0]))
        self.assertEqual(1, objects[0][0]['athleteId'])
        self.assertEqual('Tracked', objects[0][0]['trackingState'])
        self.assertGreater(objects[0][0]['box']['height'], 0)

    def test_classification_preserves_custom_geometry_schema_and_original(self):
        pose = self.sample()
        original = copy.deepcopy(pose)
        with patch('vision.pipeline.classify_exercises', return_value=[dict(athleteId=1, exercise='BenchPress')]) as classify:
            result = classify_result(pose, 'video', Path('.'), 'cpu', lambda *a: None)
        self.assertEqual(original, pose)
        self.assertEqual(original['frames'], result['frames'])
        self.assertEqual(3, result['schemaVersion'])
        self.assertEqual('custom_barbell', result['provider'])
        self.assertEqual('BenchPress', result['exercisePredictions'][0]['exercise'])
        self.assertEqual(1, len(classify.call_args.args[-1][0]))

    def test_cache_rejects_modified_predictions_or_different_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'predictions.json'
            save_predictions(path, 'key', [dict(exercise='Squat')])
            self.assertEqual([dict(exercise='Squat')], load_predictions(path, 'key'))
            self.assertIsNone(load_predictions(path, 'other'))
            value = json.loads(path.read_text())
            value['predictions'][0]['exercise'] = 'Deadlift'
            path.write_text(json.dumps(value))
            self.assertIsNone(load_predictions(path, 'key'))

    def test_classifier_is_optional_when_not_installed(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(custom_classifier_available(str(Path(temp)/'python.exe'), temp))

    def pipeline_args(self, temp):
        return SimpleNamespace(provider='custom_barbell', cache=str(Path(temp)/'cache'), input='video',
            output=str(Path(temp)/'result.json'), device='cpu', pose_model='model', pose_weights='',
            crop_padding=.2, vision_python='missing-python', models_root=temp)

    def test_pipeline_returns_valid_custom_result_without_optional_classifier(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.pipeline_args(temp)
            def pose_stage(command, start, end):
                Path(command[command.index('--output')+1]).write_text(json.dumps(self.sample()))
            with patch('pipeline.run_stage', side_effect=pose_stage), patch('pipeline.progress'):
                analyze(args)
            result = json.loads(Path(args.output).read_text())
            self.assertEqual(self.sample()['frames'], result['frames'])
            self.assertEqual(3, result['schemaVersion'])
            self.assertEqual('unavailable', result['exerciseClassificationMetadata']['status'])
            self.assertIn('manually', result['limitations'][-1])

    def test_installed_classifier_failure_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.pipeline_args(temp)
            def stage(command, start, end):
                if command[2].endswith('classify_custom.py'):
                    raise RuntimeError('classifier failed')
                Path(command[command.index('--output')+1]).write_text(json.dumps(self.sample()))
            with patch('pipeline.run_stage', side_effect=stage), patch('pipeline.progress'), \
                 patch('pipeline.custom_classifier_available', return_value=True):
                with self.assertRaisesRegex(RuntimeError, 'classifier failed'):
                    analyze(args)
            self.assertFalse(Path(args.output).exists())


if __name__ == '__main__':
    unittest.main()
