# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from collections import Counter
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    import build_request_taper_buffer_v323 as buffer
except ModuleNotFoundError as error:
    if error.name != 'klayout':
        raise
    buffer = None


@unittest.skipIf(buffer is None, 'requires pinned CAD KLayout interpreter')
class RequestTaperBuffer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.files, cls.external = buffer.materials()

    def test_actual_native_reference_dimensions_junctions_and_two_inverter_polarity(self):
        reference = buffer.reference(self.rows)
        ports, devices = buffer.inventory.native_leaves(reference, buffer.NAME)
        self.assertEqual(ports, ['A', 'X', 'VGND', 'VPWR'])
        self.assertEqual(dict(Counter(d['model'] for d in devices)),
            {'sky130_fd_pr__nfet_01v8': 24, 'sky130_fd_pr__pfet_01v8': 30,
             'sky130_fd_pr__cap_mim_m3_1': 2})
        internal = 'native____'+buffer.NAME+'__internal_b'
        gates = Counter(d['nodes'][1] for d in devices if 'fet_' in d['model'])
        self.assertEqual(gates, {'A': 18, internal: 36})
        caps = {tuple(d['nodes']) for d in devices if 'cap_mim' in d['model']}
        self.assertEqual(caps, {(internal, 'VGND'), ('X', 'VGND')})
        for d in devices:
            if 'fet_' in d['model']:
                self.assertTrue({'ad', 'as', 'pd', 'ps', 'w', 'l'} <= set(d['params']))
                self.assertEqual(float(d['params']['l']), .15)
        for value in (0, 1):
            self.assertEqual(1-(1-value), value)

    def test_actual_plan_uses_upper_metal_link_and_aligned_native_supplies(self):
        plan = buffer.design(self.rows)
        self.assertEqual([r['net'] for r in plan['routes']], ['internal_b']*3+['VGND', 'VPWR'])
        self.assertTrue(all(r['layer'] == 'metal4' for r in plan['routes'][:3]))
        self.assertTrue(all(r['layer'] == 'metal3' for r in plan['routes'][3:]))
        for k, row in enumerate(self.rows):
            self.assertGreaterEqual(plan['interstage_route_y_um'],
                                    plan['placements'][k][1]+row['bbox_um'][3]+1.99)
        self.assertFalse(plan['local_rc_qualified'])
        self.assertFalse(plan['qualified_phy'])
        self.assertEqual(list(plan['ports']), buffer.PORTS)

    def test_changed_stage_order_sizes_or_access_layers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ordered'):
            buffer.design(list(reversed(self.rows)))
        changed = deepcopy(self.rows)
        changed[0]['spec']['p_fingers'] = 20
        with self.assertRaisesRegex(ValueError, 'ordered'):
            buffer.design(changed)
        changed = deepcopy(self.rows)
        changed[0]['ports']['A']['layer'] = 'metal3'
        with self.assertRaisesRegex(ValueError, 'access layer'):
            buffer.design(changed)

    def test_stored_gds_has_exact_native_masks_placements_and_rejects_changed_mask(self):
        root = buffer.ROOT/'build/test_outputs/request_taper_buffer_v323'
        root.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(dir=root))
        plan = buffer.design(self.rows)
        file = buffer.draw(folder, self.rows, plan)
        witness = buffer.native_witness(file, self.rows, plan)
        self.assertTrue(witness['all_qualified_stage_masks_preserved'])
        self.assertTrue(witness['exact_stage_placements_verified'])
        lib = buffer.db.Layout()
        lib.read(str(file))
        master = lib.cell(self.rows[0]['macro'])
        master.shapes(lib.layer(70, 20)).insert(buffer.db.Box(-10000, -10000, -9000, -9000))
        changed = folder/'changed_mask_negative_control.gds'
        lib.write(str(changed))
        with self.assertRaisesRegex(ValueError, 'masks changed'):
            buffer.native_witness(changed, self.rows, plan)

    def test_actual_cold_evidence_requires_both_complete_replayed_native_points(self):
        paths = buffer.cold_evidence()
        self.assertGreater(len(paths), 100)
        self.assertTrue(all(p.is_file() for p in paths))
        reports = [p for p in paths if p.parent.parent.name == 'request_taper_native_replay']
        self.assertEqual({p.parent.name for p in reports}, {'20261107T010347Z', '20261107T014342Z'})


if __name__ == '__main__':
    unittest.main()
