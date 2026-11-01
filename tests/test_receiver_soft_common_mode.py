# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_soft_common_mode as soft
import matrix_receiver_soft_common_mode as matrix


class SoftCommonMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = soft.baseline.source_variant((soft.ROOT/'analog/openlvds.spice').read_text(), True)

    def network(self, variant, powered):
        changed = soft.transform(self.source, variant)
        rows = [r for r in soft.circuits(changed)[soft.TOP][1] if r[0].startswith(('XRLPP', 'XRBCPP'))]
        rails = dict(VSS=0, VREF=1.2 if powered else 0, VDDD=1.8 if powered else 0)
        names = sorted({n for r in rows for n in r[1][:2]}-set(rails)); index = {n:i for i,n in enumerate(names)}
        a = np.zeros((len(names), len(names))); b = np.zeros(len(names))
        for row in rows:
            x,y = row[1][:2]
            for u,v in [(x,y),(y,x)]:
                if u in index:
                    i = index[u]; a[i,i] += 1
                    if v in index:
                        a[i,index[v]] -= 1
                    else:
                        b[i] += rails[v]
        if not powered:
            b[index['PP']] += 1
        return np.linalg.solve(a,b)[index['PP']]

    def test_actual_series_network_centers_and_resistances(self):
        for variant, center, resistance in [('control', .9, .5), ('rail_pullup_2r', 1.08, .4), ('rail_pullup_3r', 7.2/7, 3/7)]:
            self.assertAlmostEqual(self.network(variant, True), center)
            self.assertAlmostEqual(self.network(variant, False), resistance)

    def test_only_added_unit_resistors_change_source(self):
        for variant, count in [('rail_pullup_2r',4), ('rail_pullup_3r',6)]:
            changed = soft.transform(self.source, variant)
            rows = [line for line in changed.splitlines(keepends=True) if line.startswith('XRBC')]
            self.assertEqual(len(rows), count)
            for line in rows:
                changed = changed.replace(line, '')
            self.assertEqual(changed, self.source)
            with self.assertRaises(ValueError):
                soft.transform(soft.transform(self.source, variant), variant)

    def test_former_failure_corners_gate_bulk_and_each_variant_has_own_admission(self):
        self.assertEqual(matrix.PILOTS[:2], [('sf',0), ('sf',25)])
        self.assertIn(('ss',40), matrix.PILOTS)
        reports = [dict(results=[dict(task=v, passed=True, metrics=dict(metrics=dict(passed=True)),
            twelve_device_observations=dict(observed_thin_guard_passed=True)) for v in soft.VARIANTS]) for _ in range(15)]
        reports[0]['results'][1]['passed'] = False
        gates = matrix.admission(reports)
        self.assertFalse(gates['rail_pullup_2r']['source_dc_passed'])
        self.assertTrue(gates['rail_pullup_3r']['source_dc_passed'])
        self.assertFalse(matrix.admission(reports[:5])['rail_pullup_3r']['source_dc_passed'])


if __name__ == '__main__':
    unittest.main()
