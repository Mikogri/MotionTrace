import unittest
from comparison.analyze_session import process_error

class ProcessErrorTests(unittest.TestCase):
    def test_native_crash_identifies_script_after_python_flags(self):
        command = ['python.exe', '-u', 'prepare.py', '--input', 'video.mp4']
        for code in (3221225477, -1073741819):
            message = process_error(command, code, ['  File "loader.py", line 50'])
            self.assertIn('prepare.py', message)
            self.assertIn('0xC0000005', message)
            self.assertNotIn('-u exited', message)

    def test_python_exception_is_preserved(self):
        self.assertEqual('ValueError: invalid points', process_error(['python', '-u', 'prepare.py'], 1, ['ValueError: invalid points']))

    def test_empty_error_names_script(self):
        self.assertEqual('prepare.py exited with code 7', process_error(['python', '-u', 'prepare.py'], 7, []))
