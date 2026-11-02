# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import driver_finger_banks as banks
import driver_geometric_shape as recipe
import probe_stronger_driver_shape as seed
from driver_current_variant import source_variant
from driver_gate_taper import transform
from layout import circuits, flatten


class CompactPhysicalFingerBanks(unittest.TestCase):
    def finger(self, name='M0', **changes):
        d = dict(name=name, nodes=['D', 'G', 'S', 'B'], model='sky130_fd_pr__nfet_g5v0d10v5', params=dict(w='8', l='.5'))
        d.update(changes)
        return d

    def test_same_terminals_group_but_body_model_and_geometry_do_not_mix(self):
        devices = [self.finger('M0'), self.finger('M1'), self.finger('M2', nodes=['D', 'G', 'S', 'OTHER']),
                   self.finger('M3', model='sky130_fd_pr__pfet_g5v0d10v5'),
                   self.finger('M4', params=dict(w='4', l='.5')),
                   dict(name='C0', nodes=['D', 'S'], model='sky130_fd_pr__cap_mim_m3_1', params=dict(w='36', l='36'))]
        before = deepcopy(devices)
        result = banks.group(devices)
        self.assertEqual([r['nf'] for r in result], [2, 1, 1, 1, 1])
        self.assertEqual(result[0]['members'], ['M0', 'M1'])
        self.assertEqual(result[-1]['params'], dict(w='36', l='36'))
        self.assertEqual(devices, before)
        self.assertEqual(result, banks.group(devices))
        with self.assertRaises(ValueError):
            banks.group(result)

    def test_real_candidate_retains_all_fingers_and_non_mos_devices(self):
        source = recipe.transform(seed.shaped(transform(source_variant((seed.ROOT / 'analog/openlvds.spice').read_text()), seed.VARIANT)))
        _, devices = flatten(circuits(source), recipe.taper.TOP)
        grouped = banks.group(devices)
        self.assertLess(len(grouped), len(devices))
        self.assertEqual(sum(b['nf'] for b in grouped), len(devices))
        original_other = [d for d in devices if not banks.mos(d)]
        grouped_other = [{k:v for k,v in d.items() if k not in ['nf','members']} for d in grouped if not banks.mos(d)]
        self.assertEqual(grouped_other, original_other)

    def test_unsupported_parameters_dimensions_and_duplicate_names_fail_closed(self):
        for params in [dict(w='8', l='.5', m='2'), dict(w='16', l='.5'), dict(w='nan', l='.5'), dict(w='8', l='.501')]:
            with self.assertRaises(ValueError):
                banks.group([self.finger(params=params)])
        with self.assertRaises(ValueError):
            banks.group([self.finger(), self.finger()])

    def test_pcell_recipe_exposes_each_gate_and_retains_finger_width(self):
        bank = banks.group([self.finger('M0'), self.finger('M1')])[0]
        p = banks.pcell_parameters(bank)
        self.assertEqual((p['w'], p['l'], p['nf']), ('8', '.5', 2))
        self.assertEqual((p['conn_gates'], p['guard'], p['m'], p['doports']), (0, 1, 1, 1))
        self.assertEqual((p['topc'], p['botc']), (1, 1))
        single = banks.group([self.finger()])[0]
        self.assertEqual(banks.pcell_parameters(single)['botc'], 0)
        for changed in [dict(bank, nf=1), dict(bank, nf=True), dict(bank, members=['M0', 'M0'])]:
            with self.assertRaises(ValueError):
                banks.pcell_parameters(changed)

    def test_port_roles_do_not_guess_missing_or_merged_gate_contacts(self):
        roles = banks.terminal_groups(['D0', 'D1', 'G0', 'G1', 'S1', 'B'], 2)
        self.assertEqual(roles, dict(D=['D0', 'D1'], G=['G0', 'G1'], S=['S1'], B=['B']))
        self.assertEqual(banks.terminal_groups(['D', 'G', 'S', 'B'], 1)['G'], ['G'])
        for ports in [['D0', 'D1', 'G', 'S1', 'B'], ['D0', 'G0', 'G2', 'S1', 'B'],
                      ['D0', 'G0', 'G1', 'S1'], ['D0', 'G0', 'G1', 'S1', 'B', 'OTHER']]:
            with self.assertRaises(ValueError):
                banks.terminal_groups(ports, 2)


if __name__ == '__main__':
    unittest.main()
