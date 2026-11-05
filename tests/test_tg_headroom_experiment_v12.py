# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import tg_headroom_experiment_v12 as circuit
import probe_tg_headroom_experiment_v12 as pilot
import test_tg_driver_experiment_v9 as fixtures
import native_clock_components_v2 as native


class FurtherHeadroomTests(unittest.TestCase):
    def test_only_tg_geometry_and_top_name_change_from_regular_quad(self):
        source, bank = fixtures.DriverSelectorExperimentTests().source()
        cells, root, _ = circuit.previous.transform(source, bank, 'regular_quad')
        result, changed, report = circuit.transform(source, bank, 'regular_oct')
        model = circuit.baseline.previous.tg_name(circuit.baseline.PROFILE)
        a = native.definitions(cells); b = native.definitions(result)
        self.assertEqual({k: v for k, v in a.items() if k != model}, {k: v for k, v in b.items() if k != model})
        self.assertIn('w=3.36', b[model][1][0]); self.assertIn('w=6.72', b[model][1][1])
        self.assertIn('ad=0.9744', b[model][1][0]); self.assertIn('ad=1.9488', b[model][1][1])
        self.assertEqual(changed.replace(circuit.name('regular_oct'), circuit.previous.name('regular_quad')), root)
        self.assertFalse(report['whole_bank_rc_retained']); self.assertFalse(report['qualified_phy'])

    def test_all_six_sparse_codes_remain_required(self):
        specs = pilot.specifications()
        self.assertEqual(len(specs), 6)
        self.assertEqual({(s['coarse'], s['fine']) for s in specs}, {(0, 0), (0, 1), (0, 15), (0, 16), (0, 31), (1, 0)})
        self.assertEqual({s['profile'] for s in specs}, {'regular_oct'})


if __name__ == '__main__':
    unittest.main()
