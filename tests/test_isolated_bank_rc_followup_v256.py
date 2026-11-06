# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from copy import deepcopy
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_isolated_bank_rc_followup_v256 as p

class RcFollowupTests(unittest.TestCase):
    def report(self):
        return dict(joint_rc_passed=True,isolated_bank_joint_rc_qualified=True,native_topology_verified=True,
            original_extraction_preserved=True,original_and_corrected_reductions_regenerated=True,
            native_parameters=dict(native_mos=1479,native_mims=43,newly_characterized_junction_devices=0),
            all_fine_junctions=dict(joint_rc=dict(fine_mos_with_all_measured_junction_fields=155)),
            independent_terminal_current_witness=dict(passed=True),
            passivity={k:dict(elementwise_passive_passed=True) for k in ('original_raw','corrected_raw','corrected_reduced')},
            raw_junction_correction=dict(passive_records_byte_identical=True,all_noncapacitor_devices_and_parameters_unchanged=True),
            independent_witness_input=dict(circuit_tokens_preserved=True))

    def test_every_required_rc_proof_must_pass(self):
        good=self.report();p.require_completed(good)
        for field in ('joint_rc_passed','isolated_bank_joint_rc_qualified','native_topology_verified','original_extraction_preserved','original_and_corrected_reductions_regenerated'):
            with self.subTest(field=field),self.assertRaises(ValueError):p.require_completed(dict(good,**{field:False}))
        for parent,key,value in [('independent_terminal_current_witness','passed',False),('native_parameters','newly_characterized_junction_devices',1),
                ('raw_junction_correction','passive_records_byte_identical',False),('independent_witness_input','circuit_tokens_preserved',False)]:
            bad=deepcopy(good);bad[parent][key]=value
            with self.subTest(parent=parent,key=key),self.assertRaises(ValueError):p.require_completed(bad)

    def test_negative_or_missing_passivity_evidence_cannot_be_handed_off(self):
        for label in ('original_raw','corrected_raw','corrected_reduced'):
            bad=self.report();bad['passivity'][label]['elementwise_passive_passed']=False
            with self.assertRaises(ValueError):p.require_completed(bad)
            bad=self.report();bad['passivity'].pop(label)
            with self.assertRaises(ValueError):p.require_completed(bad)

    def test_incomplete_native_physical_or_wrong_context_cannot_start_rc(self):
        for state in [dict(status='qualifying_native_gds'),dict(status='failed'),
            dict(status='native_physical_complete',artifacts=dict(native_gds='build/diagnostics/measured_balanced_native_gds_v150/6766444ea6d551f4')),
            dict(status='native_physical_complete',artifacts={})]:
            with self.assertRaises(ValueError):p.ready_native(state)

if __name__=='__main__':unittest.main()
