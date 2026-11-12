import argparse
import json
import contextlib
import io
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pipeline


class PipelineTests(unittest.TestCase):
    def test_custom_model_missing_weights_fails_before_analysis(self):
        with tempfile.TemporaryDirectory() as folder:
            args=argparse.Namespace(provider='custom_barbell',cache=folder,input='input.mp4',
                output=str(Path(folder)/'out.json'),device='cpu',pose_model='pose',pose_weights='',crop_padding=.2)
            def write_result(command,start,end):
                Path(command[command.index('--output')+1]).write_text('{}')
            with patch('pipeline.Path.is_file',return_value=False), patch('pipeline.run_stage',side_effect=write_result) as run:
                with self.assertRaisesRegex(FileNotFoundError,'shaft-v1'):
                    pipeline.analyze(args)
                run.assert_not_called()

    def test_explicit_custom_selection_does_not_require_vision_and_preserves_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            args=argparse.Namespace(provider='custom_barbell',vision_python='missing.exe',models_root='missing',
                cache=str(root/'cache'),input='input.mp4',output=str(root/'out.json'),device='cpu',
                pose_model='pose',pose_weights='',crop_padding=.2,corrections=None)
            def run(command,start,end):
                self.assertIn('custom_barbell',command)
                Path(command[command.index('--output')+1]).write_text('{"schemaVersion":3,"frames":[]}')
            with patch('pipeline.run_stage',side_effect=run) as stage:
                pipeline.analyze(args)
            self.assertEqual(1,stage.call_count)
            self.assertEqual('custom_barbell',json.loads((root/'out.json').read_text())['provider'])

    def test_process_protocol_maps_vision_progress_and_preserves_failure_cause(self):
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'stage.py'
            script.write_text('import json,sys\nprint(json.dumps(dict(type="progress",progress=.5,message="Tracking")))\nprint("Missing local checkpoint",file=sys.stderr)\nsys.exit(2)\n')
            output,errors=io.StringIO(),io.StringIO()
            with contextlib.redirect_stdout(output),contextlib.redirect_stderr(errors):
                with self.assertRaisesRegex(RuntimeError,'Missing local checkpoint'):
                    pipeline.run_stage([sys.executable,str(script)],.35,1)
            record=json.loads(output.getvalue())
            self.assertEqual(record['stage'],'Tracking')
            self.assertAlmostEqual(record['fraction'],.675)

    def test_new_provider_never_falls_back_when_vision_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);python=root/'python.exe';python.touch()
            (root/'manifest.json').write_text('{}')
            args=argparse.Namespace(provider='grounding_dino_sam2',vision_python=str(python),models_root=str(root),
                cache=str(root/'cache'),input='input.mp4',output=str(root/'out.json'),device='cuda:0',
                pose_model='pose',pose_weights='',crop_padding=.2,corrections=None)
            calls=[]
            def run(command,start,end):
                calls.append(command)
                if len(calls)==2:raise RuntimeError('vision unavailable')
            with patch('pipeline.run_stage',side_effect=run):
                with self.assertRaisesRegex(RuntimeError,'vision unavailable'):pipeline.analyze(args)
            self.assertEqual(len(calls),2)
            self.assertIn('pose_only',calls[0])
            self.assertFalse(any('custom_barbell' in c for c in calls))

    def test_missing_vision_setup_fails_before_any_model_process(self):
        args=argparse.Namespace(provider='grounding_dino_sam2',vision_python='missing-motiontrace-python.exe')
        with patch('pipeline.run_stage') as run:
            with self.assertRaises(FileNotFoundError):pipeline.analyze(args)
            run.assert_not_called()
