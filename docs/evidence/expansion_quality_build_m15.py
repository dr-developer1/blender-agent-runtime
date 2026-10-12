"""Reproduce the final M15 builds with up to four isolated Blender processes.

python -m docs.evidence.expansion_quality_build_m15 --output artifacts/quality-new
Each manual recipe and separately authored scripted-agent plan retains its own
transaction, command trace, technical report and six EEVEE diagnostic images.
This runner does not evaluate or manufacture visual scores.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time

from benchmarks.catalog import CATALOG
from benchmarks.expansion import run_manual, write_json


def run_task(name, mode, root, blender):
    directory = root / mode / name
    started = time.perf_counter()
    try:
        if mode == 'manual':
            report = run_manual(CATALOG[name], directory, executable=blender, engine='EEVEE')
        else:
            directory.mkdir(parents=True)
            # Agent CLI owns its own output subdirectory; no manual recipe reuse.
            with (directory/'execution.log').open('w') as log:
                output = directory/'build'
                result = subprocess.run([sys.executable, '-m',
                    'docs.evidence.expansion_codex_plan_m15', '--benchmark', name,
                    '--engine', 'EEVEE', '--blender', blender, '--output', str(output)],
                    stdout=log, stderr=subprocess.STDOUT, timeout=240)
            summary = json.loads((output/'summary.json').read_text())
            if result.returncode or not summary['passed']:
                raise RuntimeError(f'Agent build failed: {summary}')
            directory = output/name
            report = json.loads((directory/'report.json').read_text())
        return {'benchmark':name, 'mode':mode, 'directory':str(directory),
                'seconds':time.perf_counter()-started,
                'technical_passed':report['reports']['supported_technical_passed'],
                'outcome':report['outcome'], 'metrics':report['metrics']}
    except Exception as exc:
        return {'benchmark':name, 'mode':mode, 'directory':str(directory),
                'seconds':time.perf_counter()-started, 'technical_passed':False,
                'error_type':type(exc).__name__, 'message':str(exc)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--blender', default='blender')
    parser.add_argument('--jobs', type=int, choices=range(1,5), default=2)
    args=parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error('Output must be empty')
    records=[]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        tasks=[pool.submit(run_task,name,mode,args.output,args.blender)
               for name in CATALOG for mode in ('manual','codex_scripted_agent')]
        for future in as_completed(tasks):
            record=future.result();records.append(record)
            write_json(args.output/'summary.json', {'format_version':1,
                'expected_builds':40,'complete':len(records)==40,
                'passed':len(records)==40 and all(r['technical_passed'] for r in records),
                'records':sorted(records,key=lambda r:(r['benchmark'],r['mode']))})
            print(record['benchmark'],record['mode'],record['technical_passed'],flush=True)
    return 0 if len(records)==40 and all(r['technical_passed'] for r in records) else 1


if __name__=='__main__':
    raise SystemExit(main())
