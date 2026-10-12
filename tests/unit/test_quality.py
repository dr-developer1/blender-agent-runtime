import copy
import json
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from benchmarks.quality import audit, digest, VIEWS
from benchmarks.expansion import CATEGORIES, RUBRIC_VERSION


class QualityEvidenceTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = patch('benchmarks.quality.CATALOG', {'planter': SimpleNamespace(version=1)})
        self.catalog.start()
        self.addCleanup(self.catalog.stop)
        self.review = {'evaluator': 'test reviewer', 'rubric_version': RUBRIC_VERSION,
                       'reviews': []}
        for mode, report_mode in (('manual', 'manual'), ('codex_scripted_agent', 'agent')):
            directory = self.root / mode
            directory.mkdir()
            (directory / 'report.json').write_text(json.dumps({
                'benchmark': 'planter-v1', 'engine': 'EEVEE', 'mode': report_mode,
                'outcome': 'transaction.commit',
                'reports': {'supported_technical_passed': True}}))
            for view in VIEWS:
                (directory / (view+'.png')).write_bytes(b'observed pixels')
            self.review['reviews'].append({
                'benchmark': 'planter', 'mode': mode, 'reviewed_views': list(VIEWS),
                'scores': dict.fromkeys(CATEGORIES, 4),
                'image_sources': [{'directory': mode, 'engine': 'EEVEE',
                    'report_sha256': digest(directory/'report.json'),
                    'images_sha256': {v: digest(directory/(v+'.png')) for v in VIEWS}}]})

    def test_completed_evaluation_does_not_imply_visual_success(self):
        self.review['reviews'][0]['scores']['surface_cleanliness'] = 2
        result = audit(self.review, root=self.root)
        self.assertTrue(result['evaluation_complete'])
        self.assertFalse(result['asset_quality_passed'])
        self.assertFalse(result['full_benchmark_passed'])
        self.assertEqual(result['outcomes'][0]['below_convincing'], ['surface_cleanliness'])

    def test_reviewed_source_change_revokes_quality_pass(self):
        source = self.root / 'recipe.py'
        source.write_text('reviewed recipe')
        self.review['sources_sha256'] = {'recipe.py': digest(source)}
        self.assertTrue(audit(self.review, root=self.root)['full_benchmark_passed'])
        source.write_text('different recipe with same brief version')
        result = audit(self.review, root=self.root)
        self.assertFalse(result['evaluation_complete'])
        self.assertFalse(result['asset_quality_passed'])
        self.assertIn('Reviewed source changed: recipe.py', result['errors'])

    def test_changed_images_or_report_revoke_previously_passing_review(self):
        self.assertTrue(audit(self.review, root=self.root)['asset_quality_passed'])
        for filename in ('front.png', 'report.json'):
            with self.subTest(filename=filename):
                path = self.root / 'manual' / filename
                original = path.read_bytes()
                path.write_bytes(original+b'changed')
                result = audit(self.review, root=self.root)
                self.assertFalse(result['evaluation_complete'])
                self.assertFalse(result['asset_quality_passed'])
                path.write_bytes(original)

    def test_missing_or_duplicate_build_cannot_satisfy_suite_coverage(self):
        for reviews in (self.review['reviews'][:1], self.review['reviews']*2):
            changed = {**self.review, 'reviews': reviews}
            self.assertFalse(audit(changed, root=self.root)['evaluation_complete'])

    def test_old_brief_version_cannot_pass_by_updating_only_the_hash(self):
        path = self.root / 'manual' / 'report.json'
        report = json.loads(path.read_text())
        report['benchmark'] = 'planter-v0'
        path.write_text(json.dumps(report))
        self.review['reviews'][0]['image_sources'][0]['report_sha256'] = digest(path)
        self.assertFalse(audit(self.review, root=self.root)['evaluation_complete'])

    def test_unobserved_materials_or_boolean_scores_are_not_accepted(self):
        for change in ('engine', 'score'):
            changed = copy.deepcopy(self.review)
            if change == 'engine':
                changed['reviews'][0]['image_sources'][0]['engine'] = 'WORKBENCH'
            else:
                changed['reviews'][0]['scores']['proportions'] = True
            self.assertFalse(audit(changed, root=self.root)['evaluation_complete'])
