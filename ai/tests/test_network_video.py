import hashlib
from pathlib import Path
import tempfile
import unittest
import contextlib
import io
import sys
from comparison.analyze_session import local_video_copy, network_video, process


class NetworkVideoTests(unittest.TestCase):
    def test_banner_keeps_actual_error_while_log_keeps_traceback(self):
        log = io.StringIO()
        with contextlib.redirect_stderr(log), self.assertRaisesRegex(RuntimeError, '^ValueError: unreadable video$'):
            process([sys.executable, '-c', "raise ValueError('unreadable video')"])
        self.assertIn('Traceback', log.getvalue())

    def test_unc_is_network_input(self):
        self.assertTrue(network_video(r'\\server\films\clip.mov'))

    def test_verified_copy_can_be_reused_when_source_disconnects(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'clip.MOV'
            content = b'original video bytes'
            source.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            copied = Path(local_video_copy(source, Path(directory)/'cache', digest))
            self.assertEqual(content, copied.read_bytes())
            self.assertEqual(source.name, copied.name)
            source.unlink()
            self.assertEqual(str(copied), local_video_copy(source, Path(directory)/'cache', digest))

    def test_changed_input_does_not_publish_partial_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'clip.MOV'
            source.write_bytes(b'changed')
            cache = Path(directory)/'cache'
            with self.assertRaisesRegex(ValueError, 'changed'):
                local_video_copy(source, cache, hashlib.sha256(b'original').hexdigest())
            self.assertFalse(list(cache.rglob('*.MOV')))
            self.assertFalse(list(cache.rglob('*.tmp')))

    def test_unavailable_source_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'Reconnect'):
                local_video_copy(Path(directory)/'missing.MOV', Path(directory)/'cache', '0'*64)
