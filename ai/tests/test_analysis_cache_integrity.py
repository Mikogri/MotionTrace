import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from analyze import return_cached_analysis
from motiontrace_ai.performance import StageTimings


class AnalysisCacheIntegrityTests(unittest.TestCase):
    def check_cache(self, result, expected):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / 'cache.json'
            output = Path(folder) / 'result.json'
            cache.write_text(json.dumps(result), encoding='utf-8')
            args = SimpleNamespace(output=str(output), profile_output=None)
            with contextlib.redirect_stdout(io.StringIO()):
                accepted = return_cached_analysis(args, cache, Path('renamed.mov'), StageTimings(), 'test')
            self.assertEqual(accepted, expected)
            self.assertEqual(output.exists(), expected)
            if expected:
                saved = json.loads(output.read_text())
                self.assertEqual(saved['frames'], result['frames'])
                self.assertEqual(saved['video']['fileName'], 'renamed.mov')

    def result(self, times, duration=1):
        return dict(schemaVersion=3, video=dict(framesPerSecond=30, durationSeconds=duration),
                    frames=[dict(timestampSeconds=t, athletes=[]) for t in times])

    def test_complete_variable_rate_cache_is_used_without_resampling(self):
        self.check_cache(self.result([0, .13, .41, .9666667]), True)

    def test_truncated_cache_is_recomputed_without_copying_to_output(self):
        self.check_cache(self.result([0, 1/30], 52), False)

    def test_empty_cache_is_not_a_completed_analysis(self):
        self.check_cache(self.result([]), False)

    def test_invalid_timestamps_are_not_copied_to_output(self):
        for times in ([0, float('nan')], [0, float('inf')], [0, 0], [0, -.1]):
            with self.subTest(times=times):
                self.check_cache(self.result(times), False)

    def test_malformed_video_metadata_is_recomputed(self):
        for video in (None, [], 'bad'):
            with self.subTest(video=video):
                result = self.result([0, .9666667])
                result['video'] = video
                self.check_cache(result, False)
