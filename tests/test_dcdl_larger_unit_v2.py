# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_larger_unit_v2 as probe
import verify_dcdl_larger_unit_v2 as proof


class LargerUnitHybridTests(unittest.TestCase):
    def test_bank_changes_exactly_31_models_and_retains_driver_and_shared_shunt(self):
        original=probe.parent_source.parent_source.bank(probe.parent_source.source_core.circuit(0,4)[0])
        original=probe.parent_source.circuit(original,'core2')
        text=probe.replace_unit(original)
        self.assertEqual(text.count(probe.unit.NAME),31)
        self.assertNotIn(probe.parent_source.parent_source.UNIT,text)
        self.assertEqual(text.replace(probe.unit.NAME,probe.parent_source.parent_source.UNIT),original)
        with self.assertRaisesRegex(ValueError,'31-unit bank'):probe.replace_unit(original.replace('XU0 ','*removed ',1))

    def test_all_three_corners_require_complete_coarse_pairs_and_both_edge_overlap(self):
        rows=[]
        for spec in probe.specifications():
            coarse=spec['coarse'];zero=550 if coarse==0 else 850;full=950 if coarse==0 else 1250
            rows.append(dict(task=dict(spec=spec),error=None,result=dict(custom_mos_stress_passed=True,
                required_quarter_range_ps=[609.75,641.03],samples=[dict(code=c,rise_delay_ps=full if c==31 else zero,
                    fall_delay_ps=full if c==31 else zero) for c in spec['codes']])))
        groups=proof.groups(rows)
        self.assertEqual(len(groups),3);self.assertTrue(all(g['feasibility_passed'] for g in groups))
        rows[0]['result']['custom_mos_stress_passed']=False
        self.assertEqual(sum(not g['feasibility_passed'] for g in proof.groups(rows)),1)
        with self.assertRaisesRegex(ValueError,'coarse-pair'):proof.groups(rows[:-1])
