"""Run unittest with per-test logs and a GitHub Actions evidence summary."""
import collections
import os
from pathlib import Path
import sys
import unittest


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.modules = collections.Counter()

    def startTest(self, test):
        self.modules[test.__class__.__module__] += 1
        super().startTest(test)


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    suite = unittest.defaultTestLoader.discover('tests')
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        lines = ['## Test execution evidence', '', 'Command: `python scripts/run_tests.py` (unittest discovery).', '',
                 f'Python: `{sys.version.split()[0]}`. Tests run: **{result.testsRun}**. Failures: **{len(result.failures)}**. Errors: **{len(result.errors)}**. Skipped: **{len(result.skipped)}**.', '',
                 '| Test module | Cases executed |', '| --- | ---: |']
        lines.extend(f'| `{name}` | {count} |' for name, count in sorted(result.modules.items()))
        lines.extend(['', 'Individual test names and results appear in the Run tests job log. Counts include skipped cases. This report does not measure coverage or establish model calibration.', ''])
        with Path(summary).open('a') as output:
            output.write('\n'.join(lines))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
