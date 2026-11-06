# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from copy import deepcopy
import json
import os
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_isolated_native_physical_followup_v254 as p

class PhysicalFollowupTests(unittest.TestCase):
    def artifact(self,folder,report,state=None):
        (folder/'state.json').write_text(json.dumps(state or dict(status='complete',passed=True,qualified_phy=False)))
        (folder/'summary.json').write_text(json.dumps(report));return folder

    def test_route_handoff_requires_zero_violations_and_complete_proof(self):
        report=dict(route_bringup_passed=True,returncode=0,router_final_violations=0,connection_and_coverage_check=dict(native=True))
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.assertEqual(p.require_result(self.artifact(folder,report),'route'),report)
            for bad in [dict(report,router_final_violations=1),dict(report,connection_and_coverage_check=None)]:
                with self.assertRaises(ValueError):p.require_result(self.artifact(folder,bad),'route')
            with self.assertRaises(ValueError):p.require_result(self.artifact(folder,report,dict(status='routing')),'route')

    def test_native_handoff_rejects_failed_lvs_or_missing_final_mask_proof(self):
        report=dict(native_routed_gds_passed=True,physical=dict(passed=True,drc_count='0',lvs_passed=True),
            native_parameters=dict(native_mos=1479,native_mims=43,native_parameters_preserved=True),
            final_mask_proof=dict(complete=True),final_native_hierarchy_proof=dict(complete=True))
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.assertEqual(p.require_result(self.artifact(folder,report),'native'),report)
            failures=[dict(report,final_mask_proof=None),dict(report,final_native_hierarchy_proof=None)]
            bad=deepcopy(report);bad['physical']['lvs_passed']=False;failures.append(bad)
            bad=deepcopy(report);bad['native_parameters']['native_mos']=1453;failures.append(bad)
            for bad in failures:
                with self.assertRaises(ValueError):p.require_result(self.artifact(folder,bad),'native')

    def test_owner_restart_cannot_be_followed(self):
        live=dict(InvocationID='original',MainPID=str(os.getpid()),ActiveState='active',LoadState='loaded')
        self.assertEqual(p.owner_mode(live,'original',False),'live')
        with self.assertRaises(ValueError):p.owner_mode(dict(live,InvocationID='restarted'),'original',False)

    def test_collected_owner_needs_a_complete_receipt(self):
        missing=dict(InvocationID='',MainPID='0',ActiveState='inactive',LoadState='not-found')
        self.assertEqual(p.owner_mode(missing,'original',True),'complete')
        with self.assertRaises(ValueError):p.owner_mode(missing,'original',False)

if __name__=='__main__':unittest.main()
