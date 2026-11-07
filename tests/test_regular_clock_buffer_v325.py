# SPDX-License-Identifier: GPL-3.0-only
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    import build_regular_clock_buffer_v325 as buffer
except ModuleNotFoundError as error:
    if error.name != 'klayout':
        raise
    buffer = None


@unittest.skipIf(buffer is None, 'requires pinned CAD KLayout interpreter')
class RegularClockBuffer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows, _, _ = buffer.support.materials()
        cls.row = next(r for r in rows if r['macro'] == buffer.MODEL)

    def test_actual_reference_preserves_both_qualified_stages_and_junctions(self):
        ports, devices = buffer.support.inventory.native_leaves(buffer.reference(self.row), buffer.NAME)
        self.assertEqual(ports, buffer.PORTS)
        self.assertEqual(dict(Counter(d['model'] for d in devices)),
            {'sky130_fd_pr__nfet_01v8': 32, 'sky130_fd_pr__pfet_01v8': 40,
             'sky130_fd_pr__cap_mim_m3_1': 2})
        internal = 'native____'+buffer.NAME+'__internal_b'
        self.assertEqual(Counter(d['nodes'][1] for d in devices if 'fet_' in d['model']),
                         {'A': 36, internal: 36})
        self.assertEqual({tuple(d['nodes']) for d in devices if 'cap_mim' in d['model']},
                         {(internal, 'VGND'), ('X', 'VGND')})
        for d in devices:
            if 'fet_' in d['model']:
                self.assertTrue({'w', 'l', 'ad', 'as', 'pd', 'ps'} <= set(d['params']))
                self.assertEqual(float(d['params']['l']), .15)

    def test_plan_preserves_supplies_and_routes_interstage_above_native_masks(self):
        plan = buffer.design(self.row)
        self.assertEqual(plan['input_to_output_polarity'], 'noninverting')
        self.assertEqual(list(plan['ports']), buffer.PORTS)
        self.assertEqual([r['net'] for r in plan['routes']], ['internal_b']*3+['VGND', 'VPWR'])
        self.assertEqual([r['layer'] for r in plan['routes']], ['metal4']*3+['metal3']*2)
        self.assertGreaterEqual(plan['interstage_route_y_um'], plan['placements'][0][1]+self.row['bbox_um'][3]+1.99)
        self.assertGreater(plan['placements'][1][0]+self.row['bbox_um'][0],
                           plan['placements'][0][0]+self.row['bbox_um'][2]+7.99)
        self.assertFalse(plan['qualified_phy'])

    def test_wrong_model_size_or_pin_layer_is_rejected(self):
        for kind in ('model', 'size', 'layer'):
            row = deepcopy(self.row)
            if kind == 'model': row['macro'] = 'changed_master'
            elif kind == 'size': row['spec']['p_fingers'] = 10
            else: row['ports']['A']['layer'] = 'metal3'
            with self.assertRaises(ValueError):
                buffer.design(row)

    def test_one_native_master_two_stored_instances_and_changed_multiplicity_rejected(self):
        root = buffer.ROOT/'build/test_outputs/regular_clock_buffer_v325'
        root.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(dir=root))
        plan = buffer.design(self.row)
        file = buffer.draw(folder, self.row, plan)
        witness = buffer.native_witness(file, self.row, plan)
        self.assertTrue(witness['all_qualified_native_masks_preserved'])
        self.assertTrue(witness['exact_two_stage_placements_verified'])
        lib = buffer.db.Layout()
        lib.read(str(file))
        masters = [c for c in lib.each_cell() if c.name == buffer.MODEL]
        self.assertEqual(len(masters), 1)
        instances = list(lib.cell(buffer.NAME).each_inst())
        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[0].cell_index, instances[1].cell_index)
        lib.cell(buffer.NAME).insert(buffer.db.CellInstArray(masters[0].cell_index(), buffer.db.Trans(100000, 0)))
        changed = folder/'extra_instance_negative_control.gds'
        lib.write(str(changed))
        with self.assertRaisesRegex(ValueError, 'placements'):
            buffer.native_witness(changed, self.row, plan)


if __name__ == '__main__':
    unittest.main()
