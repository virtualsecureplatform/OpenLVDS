# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_receiver_tia_fast_clocks as handoff


class FastFrontendClockHandoff(unittest.TestCase):
    def test_only_independently_complete_passing_variants_are_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=Path(tmp);(q/'manifest.json').write_text(json.dumps(dict(identity=dict(candidate_sha256={v:'fixed' for v in ['control']+handoff.VARIANTS}))))
            gate=dict(required=15,completed=15,passed_cases=15,source_dc_passed=True)
            good=dict(diagnostic_complete=True,required_pvt=15,manifest_sha256=handoff.sha(q/'manifest.json'),variants={v:dict(gate) for v in ['control']+handoff.VARIANTS})
            self.assertEqual(handoff.admitted(q,good),handoff.VARIANTS)
            row=deepcopy(good);row['variants']['fast_tia_r2'].update(passed_cases=14,source_dc_passed=False)
            self.assertEqual(handoff.admitted(q,row),['fast_tia_r4'])
            row['variants']['fast_tia_r4'].update(passed_cases=14,source_dc_passed=False)
            self.assertEqual(handoff.admitted(q,row),[])
            for kind in ['partial','stale','control','family']:
                row=deepcopy(good)
                if kind=='partial':row['required_pvt']=6
                elif kind=='stale':row['manifest_sha256']='changed'
                elif kind=='control':row['variants']['control']['source_dc_passed']=False
                else:row['variants']['tia_r2']=row['variants'].pop('fast_tia_r2')
                with self.assertRaises(ValueError):handoff.admitted(q,row)

    def test_prior_context_is_retained_before_any_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)),patch.object(handoff.subprocess,'run') as command:
            out=Path(tmp)/'build/diagnostics/receiver_tia_fast_clock_followup/test';out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(dict(identity=dict(files={},max_parallel_variants=2,no_outer_lease=True))))
            (out/'state.json').write_text('retained')
            with self.assertRaisesRegex(ValueError,'Prior fast-frontend'):handoff.run(out)
            self.assertEqual((out/'state.json').read_text(),'retained');command.assert_not_called()

    def test_terminated_dc_owner_cannot_dispatch_clock_simulation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)),patch.object(handoff,'owner',return_value=dict(MainPID='0',ActiveState='inactive',InvocationID='')):
            out=Path(tmp)/'build/diagnostics/receiver_tia_fast_clock_followup/test';out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(dict(identity=dict(files={},max_parallel_variants=2,no_outer_lease=True,matrix='missing',unit='dc',owner=dict(MainPID='42',ActiveState='active',InvocationID='fixed')))))
            with self.assertRaisesRegex(ValueError,'terminated'):handoff.run(out)
            self.assertEqual(json.loads((out/'state.json').read_text())['status'],'held_for_diagnosis')
            self.assertFalse(list(out.glob('*_prepare.log')))

    def test_other_dc_family_is_rejected_before_owner_lookup(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)),patch.object(handoff,'owner') as owner:
            with self.assertRaisesRegex(ValueError,'fast-frontend DC matrix'):
                handoff.prepare(Path(tmp)/'build/diagnostics/receiver_tia_matrix/other',Path(tmp)/'build/diagnostics/receiver_clamp/reference','dc')
            owner.assert_not_called()


if __name__=='__main__':unittest.main()
