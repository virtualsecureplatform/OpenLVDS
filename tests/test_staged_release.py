# SPDX-License-Identifier: GPL-3.0-only
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dll_native_evidence as native
from staged_release import proof_binding


class NativeReleaseCoverage(unittest.TestCase):
    def test_release_requires_clock_extremes_all_pvt_and_asymmetric_stuck_faults(self):
        req=json.loads((native.ROOT/'requirements.json').read_text())
        cases=native.required_cases(req)
        for spec in [dict(kind='loop',process='ss',temperature=0,mhz=410,duty=.55),
                     dict(kind='loop',process='ff',temperature=0,mhz=390,duty=.45),
                     dict(kind='loop',process='sf',temperature=40,mhz=400,duty=.5),
                     dict(kind='logic',process='fs',temperature=25,up=0,dn=1.8),
                     dict(kind='phase',process='ss',temperature=40,mhz=400,offset_ps=-150,reference_slew_ps=20,feedback_slew_ps=200)]:
            self.assertIn(native.signature(spec),cases)
        self.assertNotIn(native.signature(dict(kind='loop',process='ss',temperature=0,mhz=420,duty=.55)),cases)

    def test_missing_duplicate_and_charge_pump_cases_cannot_pass_coverage(self):
        task=dict(id='loop',fast_rc=False,spec=dict(kind='loop',architecture='averaged_pfd_ota'))
        manifest=dict(tasks=[task],identity={})
        expected={native.signature(task['spec'])}
        with patch.object(native,'required_cases',return_value=expected):
            self.assertEqual(set(native.check_coverage(manifest,{})),{'loop'})
            for tasks in [[],[task,copy.deepcopy(task)]]:
                with self.assertRaisesRegex(ValueError,'coverage'):native.check_coverage(dict(manifest,tasks=tasks),{})
            changed=copy.deepcopy(task);changed['spec']['architecture']='charge_pump'
            with self.assertRaisesRegex(ValueError,'OTA architecture'):native.check_coverage(dict(manifest,tasks=[changed]),{})

    def test_logic_fixture_cannot_accept_stuck_quiet(self):
        task=dict(id='stuck',fast_rc=False,spec=dict(kind='logic',expected=False))
        with patch.object(native,'required_cases',return_value={native.signature(task['spec'])}):
            with self.assertRaisesRegex(ValueError,'require a fault'):
                native.check_coverage(dict(tasks=[task],identity={}),{})


class ReleaseProofBinding(unittest.TestCase):
    def test_proof_from_other_candidate_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'another native DLL candidate'):
            proof_binding(Path('/candidate_b/recovery/hash/summary.json'),Path('/candidate_a'))

    def test_proofs_must_share_the_selected_model_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            q=Path(directory).resolve();folder=q/'readiness/hash';folder.mkdir(parents=True)
            report=folder/'summary.json';model=q/'stability/hash/summary.json';recovery=q/'recovery/hash/summary.json'
            (folder/'manifest.json').write_text(json.dumps(dict(identity=dict(stability=str(model),recovery=str(recovery)))))
            proof_binding(report,q,model,recovery)
            with self.assertRaisesRegex(ValueError,'another stability'):
                proof_binding(report,q,q/'stability/other/summary.json',recovery)
            with self.assertRaisesRegex(ValueError,'another recovery'):
                proof_binding(report,q,model,q/'recovery/other/summary.json')
