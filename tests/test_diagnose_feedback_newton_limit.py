# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_feedback_newton_limit as diagnostic


class FeedbackNewtonBudget(unittest.TestCase):
    def test_only_iteration_budget_and_include_path_change(self):
        parent=Path('/work/OpenLVDS/parent');out=Path('/work/OpenLVDS/new')
        text='Diagnostic\n.include "'+str(parent)+'/library.spice"\n.options method=gear reltol=1e-4 abstol=1e-12\n.tran 20p 188.049n 0 1p\n.print tran V(Q)\n.end\n'
        actual=diagnostic.deck_with_budget(text,parent,out)
        self.assertEqual(actual.replace('.options itl4=100\n','').replace(str(out),str(parent)),text)
        for bad in [actual.replace(str(out),str(parent)),text.replace('188.049n','100n'),text.replace('0 1p','0 20p')]:
            with self.assertRaises(ValueError):diagnostic.deck_with_budget(bad,parent,out)

    def test_host_preparation_keeps_container_library_paths(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(diagnostic,'ROOT',Path(tmp)):
            parent=Path(tmp)/'build/diagnostics/receiver_feedback_link_diagnostic/old'
            out=parent.with_name('new')
            text='Diagnostic\n.include "/work/OpenLVDS/build/diagnostics/receiver_feedback_link_diagnostic/old/library.spice"\n.tran 20p 188.049n 0 1p\n.end\n'
            actual=diagnostic.deck_with_budget(text,parent,out)
            self.assertIn('/work/OpenLVDS/build/diagnostics/receiver_feedback_link_diagnostic/new/library.spice',actual)
            self.assertNotIn(tmp,actual)

    def test_live_and_successful_owners_cannot_be_treated_as_numerical_failure(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(diagnostic,'ROOT',Path(tmp)):
            p=Path(tmp)/'build/diagnostics/receiver_feedback_link_diagnostic/test'
            for state in [dict(MainPID='42',ActiveState='active',Result='success'),dict(MainPID='0',ActiveState='inactive',Result='success')]:
                with patch.object(diagnostic,'owner',return_value=state):
                    with self.assertRaisesRegex(ValueError,'terminal failed owner'):diagnostic.prepare(p,'unit')

    def test_terminal_result_without_timestep_collapse_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(diagnostic,'ROOT',Path(tmp)),patch.object(diagnostic,'owner',return_value=dict(MainPID='0',ActiveState='failed',Result='exit-code',ExecStart='scripts/probe_corrected_driver_tia_diagnostic.py run build/diagnostics/receiver_feedback_link_diagnostic/test')):
            p=Path(tmp)/'build/diagnostics/receiver_feedback_link_diagnostic/test';p.mkdir(parents=True)
            (p/'ngspice.log').write_text('An unrelated error; preserve for diagnosis')
            with self.assertRaisesRegex(ValueError,'recorded terminal transient'):diagnostic.prepare(p,'unit')
            self.assertEqual((p/'ngspice.log').read_text(),'An unrelated error; preserve for diagnosis')


    def test_failed_owner_of_another_context_cannot_authorize_derivation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(diagnostic,'ROOT',Path(tmp)),patch.object(diagnostic,'owner',return_value=dict(MainPID='0',ActiveState='failed',Result='exit-code',ExecStart='scripts/probe_corrected_driver_tia_diagnostic.py run build/diagnostics/receiver_feedback_link_diagnostic/other')):
            with self.assertRaisesRegex(ValueError,'another diagnostic context'):
                diagnostic.prepare(Path(tmp)/'build/diagnostics/receiver_feedback_link_diagnostic/test','unit')


if __name__=='__main__':unittest.main()
