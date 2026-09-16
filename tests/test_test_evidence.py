"""Execution reports must preserve failure exits and observed counts."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1] / 'scripts' / 'run_tests.py'


class TestEvidenceTests(unittest.TestCase):
    def test_real_runner_reports_failures_skips_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tests').mkdir()
            (root / 'tests' / 'test_sample.py').write_text('''import unittest
class Sample(unittest.TestCase):
    def test_pass(self): pass
    def test_fail(self): self.fail("deliberate failure")
    @unittest.skip("deliberate skip")
    def test_skip(self): pass
''')
            summary = root / 'summary.md'
            result = subprocess.run([sys.executable, str(RUNNER)], cwd=root, env=dict(os.environ, GITHUB_STEP_SUMMARY=str(summary)), capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('test_fail', result.stderr)
            text = summary.read_text()
            self.assertIn('Tests run: **3**', text)
            self.assertIn('Failures: **1**', text)
            self.assertIn('Skipped: **1**', text)
            self.assertIn('| `test_sample` | 3 |', text)
