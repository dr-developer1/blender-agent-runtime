"""Run real-Blender conformance and save timed, machine-readable evidence."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import time
import unittest


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def startTest(self, test):
        self.started = time.perf_counter()
        self.status = 'passed'
        self.reason = None
        super().startTest(test)

    def addFailure(self, test, err):
        self.status = 'failed'
        super().addFailure(test, err)

    def addError(self, test, err):
        self.status = 'error'
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.status, self.reason = 'skipped', reason
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self.status = 'failed'
        super().addSubTest(test, subtest, err)

    def stopTest(self, test):
        record = {'test': test.id(), 'status': self.status,
                  'seconds': time.perf_counter() - self.started}
        if self.reason:
            record['reason'] = self.reason
        if hasattr(test, 'metrics'):
            record['metrics'] = test.metrics
        self.records.append(record)
        super().stopTest(test)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/conformance.json'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suite = unittest.defaultTestLoader.discover(str(root / 'conformance'), top_level_dir=str(root))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    complete = result.wasSuccessful() and not result.skipped and result.testsRun > 0
    report = {'format_version': 1, 'timestamp': datetime.now(timezone.utc).isoformat(),
              'python_version': platform.python_version(), 'platform': platform.platform(),
              'blender_executable': os.environ.get('BLENDER_EXECUTABLE', 'blender'),
              'passed': complete, 'tests_run': result.testsRun, 'skipped': len(result.skipped),
              'tests': result.records,
              'failures': [{'test': test.id(), 'traceback': trace}
                           for test, trace in result.failures + result.errors]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Conformance evidence: {args.output}')
    return 0 if complete else 1


if __name__ == '__main__':
    sys.exit(main())
