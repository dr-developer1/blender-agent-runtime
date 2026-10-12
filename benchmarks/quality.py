"""Verify reviewed benchmark artifacts: python -m benchmarks.quality --review FILE.

An evaluated milestone and a convincing asset are separate outcomes. Scores of
four or five in every category are required for the latter visual gate. Neither
outcome certifies manufacturing, physical safety or production readiness.
"""
import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.catalog import CATALOG
from benchmarks.expansion import CATEGORIES, RUBRIC_VERSION, write_json

VIEWS = ('front', 'back', 'left', 'right', 'top', 'perspective')
MODES = ('manual', 'codex_scripted_agent')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(review, *, root=Path('.')):
    """Fail closed on missing, stale or incomplete evidence, without editing it."""
    errors, outcomes, seen = [], [], set()
    if not review.get('evaluator') or review.get('rubric_version') != RUBRIC_VERSION:
        errors.append('Missing evaluator or unsupported rubric version')
    for filename, expected_digest in review.get('sources_sha256', {}).items():
        try:
            if digest(root / filename) != expected_digest:
                errors.append(f'Reviewed source changed: {filename}')
        except OSError as exc:
            errors.append(f'Reviewed source unavailable: {filename}: {exc}')
    for entry in review.get('reviews', []):
        name, mode = entry.get('benchmark'), entry.get('mode')
        key = (name, mode)
        if name not in CATALOG or mode not in MODES or key in seen:
            errors.append(f'Unknown or duplicate review: {key}')
            continue
        seen.add(key)
        scores = entry.get('scores', {})
        valid_scores = (set(scores) == set(CATEGORIES) and all(
            type(v) is int and 1 <= v <= 5 for v in scores.values()))
        if not valid_scores or set(entry.get('reviewed_views', [])) != set(VIEWS):
            errors.append(f'Incomplete scores or views: {key}')
        sources = entry.get('image_sources', [])
        if not sources or not any(s.get('engine') == 'EEVEE' for s in sources):
            errors.append(f'Missing material observation: {key}')
        technical_passed = bool(sources)
        for source in sources:
            directory = root / source['directory']
            try:
                report_path = directory / 'report.json'
                if digest(report_path) != source.get('report_sha256'):
                    raise ValueError('technical report hash mismatch')
                report = json.loads(report_path.read_text())
                if (report['benchmark'] != f'{name}-v{CATALOG[name].version}' or
                        report['engine'] != source['engine'] or
                        report.get('outcome') != 'transaction.commit' or
                        (mode == 'manual' and report['mode'] != 'manual') or
                        (mode == 'codex_scripted_agent' and report['mode'] != 'agent')):
                    raise ValueError('report identity mismatch')
                technical_passed &= report['reports']['supported_technical_passed'] is True
                hashes = source['images_sha256']
                if set(hashes) != set(VIEWS):
                    raise ValueError('incomplete image hashes')
                for view in VIEWS:
                    if digest(directory / (view+'.png')) != hashes[view]:
                        raise ValueError(f'{view} image hash mismatch')
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f'{key}: {exc}')
                technical_passed = False
        weak = [category for category in CATEGORIES
                if not valid_scores or scores[category] < 4]
        outcomes.append({'benchmark': name, 'mode': mode,
                         'technical_passed': technical_passed,
                         'visual_rubric_passed': valid_scores and not weak,
                         'benchmark_passed': technical_passed and valid_scores and not weak,
                         'below_convincing': weak,
                         'notes': entry.get('notes', '')})
    expected = {(name, mode) for name in CATALOG for mode in MODES}
    if seen != expected:
        errors.append(f'Missing reviews: {sorted(expected-seen)}')
    evaluated = not errors and all(o['technical_passed'] for o in outcomes)
    return {'format_version': 1, 'rubric_version': RUBRIC_VERSION,
            'visual_threshold': 4, 'expected_reviews': len(expected),
            'evaluation_complete': evaluated,
            'asset_quality_passed': evaluated and all(o['visual_rubric_passed'] for o in outcomes),
            'full_benchmark_passed': evaluated and all(o['benchmark_passed'] for o in outcomes),
            'production_readiness': 'unassessed', 'errors': errors, 'outcomes': outcomes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--require-quality', action='store_true')
    args = parser.parse_args()
    result = audit(json.loads(args.review.read_text()))
    write_json(args.output, result)
    print(json.dumps({key: result[key] for key in
        ('evaluation_complete', 'asset_quality_passed', 'expected_reviews', 'errors')}))
    return 0 if result['asset_quality_passed' if args.require_quality else 'evaluation_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
