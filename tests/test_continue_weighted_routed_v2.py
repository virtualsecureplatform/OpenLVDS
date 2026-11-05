# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_weighted_routed_v2 as followup


class RoutedFollowupTests(unittest.TestCase):
    def owners(self):return {r:dict(ActiveState='active',MainPID=str(p),InvocationID=r+'-original') for r,p in [('producer',17),('verification',19)]}

    def test_absent_or_running_state_waits_only_on_the_exact_live_owners(self):
        expected=self.owners()
        for state in [None,{'status':'running'}]:
            self.assertEqual(followup.disposition(state,None,self.owners(),expected),'waiting_physical_fine_control')
            for role in expected:
                observed=self.owners();observed[role]['InvocationID']='restarted'
                with self.assertRaises(ValueError):followup.disposition(state,None,observed,expected)
                observed=self.owners();observed[role].update(ActiveState='failed',MainPID='0')
                with self.assertRaises(ValueError):followup.disposition(state,None,observed,expected)

    def test_completed_waveforms_still_wait_for_the_matching_independent_receipt(self):
        state=dict(status='fine_control_pilot_complete',cases=4,errors=0);owners=self.owners()
        self.assertEqual(followup.disposition(state,None,owners,owners),'waiting_control_verification')
        self.assertEqual(followup.disposition(state,Path('/matching'),owners,owners),'ready_for_gate')
        for changed in [dict(state,errors=1),dict(state,cases=2),{'status':'held_for_diagnosis'}]:
            with self.assertRaises(ValueError):followup.disposition(changed,Path('/matching'),owners,owners)

    def test_receipt_selection_ignores_other_campaigns_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);controls=root/'build/diagnostics/weighted_fine_control_v4/chosen'
            receipts=root/'build/diagnostics/weighted_fine_control_verification_v4'
            def write(name,parent):
                p=receipts/name;p.mkdir(parents=True);(p/'summary.json').write_text(json.dumps({'identity':{'parent':parent}}));return p
            write('unrelated','build/diagnostics/weighted_fine_control_v4/other')
            self.assertIsNone(followup.receipt_for(controls,root))
            expected=write('matching',str(controls.relative_to(root)))
            self.assertEqual(followup.receipt_for(controls,root),expected)
            write('second',str(controls.relative_to(root)))
            with self.assertRaises(ValueError):followup.receipt_for(controls,root)


if __name__=='__main__':unittest.main()
