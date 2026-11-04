# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_tg_buffered_v2 as circuit
import probe_dcc_tg_buffered_v2 as pilot
import verify_dcc_static_pilots_v4 as verifier
import test_dcc_tg_combiner_v2 as fixture


class BufferedRealTgDccTests(unittest.TestCase):
    def test_all_tg_controls_and_data_are_buffered_and_storage_is_gate_loaded(self):
        library=fixture.RealTgDccTests().library()
        library+='.subckt sky130_fd_sc_hd__buf_8 A VGND VNB VPB VPWR X\nX0 X A private VGND sky130_fd_pr__nfet_01v8 w=.64 l=.15\n.ends\n'
        text,nodes=circuit.source('tg1',library);mos=circuit.devices(text)
        raw={'a','a_qb','b','b_qb'}
        for d in mos:
            if d['name'].startswith('Xtg_'):
                self.assertTrue(d['nodes'][1].endswith('_iso'))
                self.assertTrue(d['nodes'][2].endswith('_iso'))
                self.assertFalse(raw&set(d['nodes']))
        self.assertEqual(nodes['isolation_nodes'],{n:n+'_iso' for n in raw})
        self.assertEqual(len(nodes['output_nodes']),28)
        for n in raw:self.assertIn('Xisolate_'+n+'__X0 '+n+'_iso '+n+' ',text)

    def test_contract_mean_gate_is_separate_from_individual_cycle_diagnostics(self):
        report=dict(pilot_passed=True,maximum_individual_half_cycle_error_ps=150)
        with patch.object(pilot,'measure',return_value=report),patch.object(circuit,'devices',return_value=[]):
            result=pilot.assess(Path('/fixture'),{},'')
        self.assertTrue(result['pilot_passed']);self.assertFalse(result['individual_half_cycle_50ps_diagnostic_passed'])
        required=verifier.requirements(dict(startup_passed=True,event_integrity_passed=True,half_cycle_passed=True,
            terminal_screen_passed=True,maximum_individual_half_cycle_error_ps=150))
        self.assertTrue(all(required.values()));self.assertNotIn('every_half_cycle_passed',required)

    def test_independent_numeric_comparison_rejects_bool_and_nonfinite_changes(self):
        self.assertFalse(verifier.same(True,1));self.assertFalse(verifier.same(float('nan'),float('nan')))
        self.assertFalse(verifier.same(float('inf'),float('inf')))
        self.assertFalse(verifier.same({'x':[1,2]},{'x':[1,3]}))
        self.assertTrue(verifier.same({'x':[1.,2.]},{'x':[1.,2.+1e-9]}))


if __name__=='__main__':unittest.main()
