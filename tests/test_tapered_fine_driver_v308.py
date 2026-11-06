# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
try:
    import qualify_tapered_fine_driver_rc_v309 as rc
except ModuleNotFoundError as error:
    if error.name not in ('klayout', 'pya'):
        raise
    rc = None


@unittest.skipIf(rc is None, 'requires CAD KLayout environment')
class TaperedFineDriver(unittest.TestCase):
    def test_native_bulk_and_gate_connections_and_loading_profiles(self):
        physical = rc.physical
        self.assertEqual(physical.PROFILES, [dict(p_fingers=6, n_fingers=4),
                                             dict(p_fingers=10, n_fingers=8)])
        for spec in physical.PROFILES:
            ports, devices = physical.inventory.native_leaves(
                physical.schematic(spec), physical.name(spec))
            self.assertEqual(ports, ['A', 'Y', 'VGND', 'VPWR'])
            counts = {}
            for device in devices:
                model = device['model']
                counts[model] = counts.get(model, 0) + 1
                if 'nfet' in model:
                    self.assertEqual(device['nodes'], ['Y', 'A', 'VGND', 'VGND'])
                    self.assertEqual(device['params'], dict(w='0.65', l='.15'))
                elif 'pfet' in model:
                    self.assertEqual(device['nodes'], ['Y', 'A', 'VPWR', 'VPWR'])
                    self.assertEqual(device['params'], dict(w='1.0', l='.15'))
                else:
                    self.assertEqual(model, physical.CAP)
                    self.assertEqual(device['nodes'], ['Y', 'VGND'])
                    self.assertEqual(device['params'], dict(w='2', l='2'))
            self.assertEqual(counts, {'sky130_fd_pr__nfet_01v8': spec['n_fingers'],
                                     'sky130_fd_pr__pfet_01v8': spec['p_fingers'],
                                     physical.CAP: 1})

    def test_reject_partial_failed_or_mismatched_physical_evidence(self):
        rows = [dict(spec=spec, macro=rc.physical.name(spec), passed=True,
                     lvs_passed=True, native_inventory_passed=True, drc_count='0')
                for spec in rc.physical.PROFILES]
        state = dict(status='complete', passed=True, qualified_phy=False)
        report = dict(passed=True, rows=rows)
        rc.require_physical(state, report)
        for index in range(2):
            for key, value in [('passed', False), ('lvs_passed', False),
                               ('native_inventory_passed', False), ('drc_count', '1'),
                               ('spec', dict(p_fingers=20, n_fingers=16)),
                               ('macro', 'unqualified_replacement')]:
                bad = deepcopy(report)
                bad['rows'][index][key] = value
                with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                    rc.require_physical(state, bad)
        with self.assertRaises(ValueError):
            rc.require_physical(state, dict(report, rows=rows[:1]))
        with self.assertRaises(ValueError):
            rc.require_physical(dict(state, status='routing'), report)

    def test_actual_native_layout_inventory_terminals_and_dimensions(self):
        parent = rc.ROOT / 'build/diagnostics/tapered_fine_driver_physical_v308/e54a2292b8e29d55'
        if not (parent / 'summary.json').exists():
            self.skipTest('requires retained actual tapered native layouts')
        rc.physical.bound(parent)
        for spec in rc.physical.PROFILES:
            name = rc.physical.name(spec)
            text = (parent / name / (name + '.lvs.spice')).read_text()
            result = rc.census(text, name, spec)
            self.assertEqual(result['native_primitives'],
                             spec['p_fingers'] + spec['n_fingers'] + 1)
            _, devices = rc.inventory.native_leaves(text, name + '_flat')
            for device in devices:
                model = device['model']
                if 'fet_' in model:
                    supply = 'VGND' if 'nfet' in model else 'VPWR'
                    self.assertEqual(device['nodes'][1], 'A')
                    self.assertEqual(device['nodes'][3], supply)
                    self.assertEqual(set(device['nodes'][::2]), {'Y', supply})
                    number = rc.inventory.exact_number
                    self.assertEqual(number(device['params']['w']),
                                     number('.65' if 'nfet' in model else '1'))
                    self.assertEqual(number(device['params']['l']), number('.15'))
                else:
                    self.assertEqual(set(device['nodes']), {'Y', 'VGND'})
            with self.assertRaises(ValueError):
                rc.census(text.replace('sky130_fd_pr__pfet_01v8',
                                       'sky130_fd_pr__pfet_01v8_hvt', 1), name, spec)
            with self.assertRaises(ValueError):
                rc.census(text.replace(' A Y VGND VPWR', ' Y A VGND VPWR', 1),
                          name, spec)


if __name__ == '__main__':
    unittest.main()
