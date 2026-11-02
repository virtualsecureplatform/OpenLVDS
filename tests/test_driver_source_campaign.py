# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import itertools
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import driver_source_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]


class SourcePilotCampaign(unittest.TestCase):
    def test_full_eighty_ns_trace_is_required(self):
        good = np.array([[0., 0., 1.], [1., 80e-9, 1.]])
        with patch.object(campaign.reference.shape, 'read_wave', return_value=(good, {})):
            self.assertIs(campaign.completed_wave(Path('/trace'))[0], good)
        for bad in [good * .5, np.array([[0., 0., 1.], [1., 80e-9, np.nan]]), good[::-1]]:
            with patch.object(campaign.reference.shape, 'read_wave', return_value=(bad, {})):
                with self.assertRaises(ValueError):
                    campaign.completed_wave(Path('/trace'))

    def fixture(self, root, stage):
        req = json.loads((ROOT / 'requirements.json').read_text())
        (root / 'requirements.json').write_text(json.dumps(req))
        recipe_path = root / 'scripts/recipe.py'
        recipe_path.parent.mkdir()
        recipe_path.write_text('bounded recipe')
        (recipe_path.parent / Path(campaign.__file__).name).write_bytes(Path(campaign.__file__).read_bytes())
        recipe = SimpleNamespace(__file__=str(recipe_path), NEW='recipe', POINTS=[('tt', 25), ('ss', 25), ('ff', 40)])
        points = recipe.POINTS if stage == 'pilot' else list(itertools.product(req['process_corners'], req['temperatures_c']))
        identity = dict(recipe='recipe', stage=stage, points=[list(p) for p in points],
            inputs={}, code={recipe_path.name:campaign.sha(recipe_path),
                            Path(campaign.__file__).name:campaign.sha(Path(campaign.__file__))}, simulator='engine')
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
        out = root / 'build/diagnostics' / ('driver_source_pilot' if stage == 'pilot' else 'driver_shape_source') / fingerprint
        out.mkdir(parents=True)
        tasks = campaign.tasks(points)
        for t in tasks:
            folder = out / t['id']
            folder.mkdir()
            for n in ['source.spice', 'bench.cir']:
                (folder / n).write_text(n)
            t['files'] = {n:campaign.sha(folder / n) for n in ['source.spice', 'bench.cir']}
        (out / 'manifest.json').write_text(json.dumps(dict(identity=identity, tasks=tasks)))
        return out, recipe

    def test_missing_case_cannot_narrow_full_pvt_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out, recipe = self.fixture(root, 'full')
            with patch.object(campaign, 'ROOT', root), patch.object(campaign, 'provenance', return_value='engine'):
                self.assertEqual(len(campaign.context(out, recipe)['tasks']), 30)
                p = out / 'manifest.json'
                m = json.loads(p.read_text())
                m['tasks'].pop()
                p.write_text(json.dumps(m))
                with self.assertRaisesRegex(ValueError, 'coverage'):
                    campaign.context(out, recipe)

    def test_incomplete_pilot_admission_never_runs_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out, recipe = self.fixture(root, 'pilot')
            recipe.measure = lambda *a: self.fail('Partial pilot measured')
            with patch.object(campaign, 'ROOT', root), patch.object(campaign, 'provenance', return_value='engine'):
                with self.assertRaisesRegex(ValueError, 'Complete every'):
                    campaign.verified(out, recipe)

    def test_partial_scientific_output_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out, recipe = self.fixture(root, 'pilot')
            (out / 'tt_25_negative_op/bench.raw').write_text('partial')
            with patch.object(campaign, 'ROOT', root), patch.object(campaign, 'provenance', return_value='engine'), \
                    patch.object(campaign, 'lease', side_effect=AssertionError('Partial case retried')):
                with self.assertRaisesRegex(ValueError, 'partial source output'):
                    campaign.run(out, recipe)


if __name__ == '__main__':
    unittest.main()
