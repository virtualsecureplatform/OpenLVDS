# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_balanced_drive_v2 as probe
import verify_dcdl_balanced_drive_v2 as proof


class BalancedDriveTests(unittest.TestCase):
    def test_same_parallel_hardware_for_both_coarse_codes(self):
        for coarse in [0,1]:
            source=probe.parent_source.bank(probe.source_core.circuit(coarse,4)[0])
            for variant,count in probe.VARIANTS.items():
                text=probe.circuit(source,variant)
                rows=[line.split() for line in text.splitlines() if line.startswith('X')]
                self.assertEqual(sum(r[-1]==probe.parent_source.UNIT for r in rows),31)
                for original in source.splitlines():
                    words=original.split()
                    if not words or not words[-1].startswith('sky130_fd_sc_hd__'):continue
                    copies=count if words[0]=='Xout' else 2
                    matched=[r for r in rows if r[0]==words[0] or r[0].startswith(words[0]+'_parallel')]
                    self.assertEqual(len(matched),copies)
                    self.assertTrue(all(r[1:]==words[1:] for r in matched))
                self.assertIn('XCKICK r0 VSS sky130_fd_pr__cap_mim_m3_1 w=4 l=4',text)

    def test_fixture_has_exact_unit_library_once_and_no_duplicate_control_shunt(self):
        import os
        from unittest.mock import patch
        spec=probe.specifications()[1]
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            text=probe.fixture(Path('/context'),spec,[])
        self.assertEqual(text.count('.include "/context/unit_rc.spice"'),1)
        self.assertIn('.include "/context/coarse1_core2.spice"',text)
        self.assertNotIn('XCEB',text)
        self.assertNotIn('V(XD:cap',text)

    def test_incomplete_or_unexpected_core_is_rejected(self):
        source=probe.parent_source.bank(probe.source_core.circuit(0,4)[0])
        incomplete='\n'.join(line for line in source.splitlines() if not line.startswith('Xin '))+'\n'
        with self.assertRaisesRegex(ValueError,'complete 16-stage'):probe.circuit(incomplete,'core2')
        with self.assertRaisesRegex(ValueError,'Unknown balanced'):probe.circuit(source,'typo')

    def test_verdict_uses_worst_first_or_repeated_edge_and_actual_overlap(self):
        def row(coarse,samples):
            return dict(task=dict(spec=dict(variant='core2',coarse=coarse)),error=None,
                result=dict(samples=[dict(code=c,rise_delay_ps=d,fall_delay_ps=d) for c,d in samples],
                    custom_mos_stress_passed=True,required_quarter_range_ps=[609.75,641.03]))
        rows=[row(0,[(0,610),(31,900),(0,600)]),row(1,[(0,850),(31,1100),(0,840)])]
        verdict=proof.candidate(rows,'core2')
        self.assertFalse(verdict['feasibility_passed']);self.assertEqual(verdict['fast_quarter_headroom_ps'],-.25)
        rows[0]['result']['samples'][0]['rise_delay_ps']=590
        self.assertTrue(proof.candidate(rows,'core2')['feasibility_passed'])
        rows[1]['result']['samples'][0]['rise_delay_ps']=901
        self.assertFalse(proof.candidate(rows,'core2')['feasibility_passed'])
        with self.assertRaisesRegex(ValueError,'coarse-pair'):proof.candidate(rows[:1],'core2')
