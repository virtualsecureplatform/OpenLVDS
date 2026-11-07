"""Exercise actual native buffer widths and counter placement failure cases."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import plan_request_taper_counter_v327 as planner


class NativeCounterPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load real component dimensions/pin accesses without rehashing all
        # historical native waveforms. The producer separately binds those.
        identity = json.loads((planner.PREFLIGHT/'manifest.json').read_text())['identity']
        cls.cells = identity['cells']
        cls.macros = deepcopy(identity['macros'])
        physicals = {
            planner.materials.REQ: ROOT/'build/diagnostics/request_taper_buffer_physical_v323/8cfc7cf7b15b78c9',
            planner.materials.CLK: planner.materials.CLOCK}
        for name, folder in physicals.items():
            r = json.loads((folder/'summary.json').read_text())
            row = dict(r['physical'], ports=r['ports'], macro=name,
                gds_sha256=r['gds_sha256'], lef_sha256=r['lef_sha256'])
            cls.macros[name] = planner.assembly.macro(name, ROOT/cls.macros[name]['folder'], row)

    def test_existing_plan_overlaps_both_actual_parallel_buffers(self):
        old = planner.routing.strong_plan(self.cells, self.macros, planner.assembly.default_plan())
        self.assertEqual(planner.overlaps(self.cells, self.macros, old['placements']),
            [['clock_driver', 'clock_driver_parallel'], ['request_driver', 'request_driver_parallel']])

    def test_wider_corridor_fits_actual_buffers_without_changing_cells(self):
        cells, macros = deepcopy(self.cells), deepcopy(self.macros)
        result = planner.plan(cells, macros)
        self.assertEqual(cells, self.cells)
        self.assertEqual(macros, self.macros)
        self.assertEqual(result['configuration']['corridor_um'], 40.)
        self.assertEqual(planner.overlaps(cells, macros, result['placements']), [])
        self.assertAlmostEqual(result['parallel_buffer_footprint_gaps_um']['clock_driver'], 4.16)
        self.assertAlmostEqual(result['parallel_buffer_footprint_gaps_um']['request_driver'], 8.96)

    def test_future_oversized_buffer_is_rejected(self):
        macros = deepcopy(self.macros)
        macros[planner.materials.CLK]['bbox'][2] += 1000
        with self.assertRaisesRegex(ValueError, 'footprints overlap'):
            planner.plan(self.cells, macros)

    def test_clock_feedback_pin_map_is_rejected(self):
        cells = deepcopy(self.cells)
        next(c for c in cells if c['name'] == 'clock_driver')['pins']['A'] = 'CLK'
        with self.assertRaisesRegex(ValueError, 'role, polarity or public pins'):
            planner.plan(cells, self.macros)


if __name__ == '__main__':
    unittest.main()
