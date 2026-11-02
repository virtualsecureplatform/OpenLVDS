# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import restore_baseline_coupled as restore


class PreferredBaselineRestoration(unittest.TestCase):
    def fixture(self):
        leaves=['PP','PN','CO','CL','CT','RESTORE0','RESTORE1']
        model='.subckt openlvds_receiver_core P N Q\n'+'\n'.join(f'R{i} openlvds_receiver_core__{leaf}.t1 Q 1' for i,leaf in enumerate(leaves))+'\n.ends openlvds_receiver_core\n'
        deck='Coupled\n.print tran V(Q0) '+' '.join(f'V(X{instance}:openlvds_receiver_core__{leaf}.t99)' for instance in ['DR','CR'] for leaf in leaves)+'\n.end\n'
        return deck,model

    def test_only_internal_receiver_probes_are_rebound(self):
        deck,model=self.fixture();actual=restore.receiver_probes(deck,model)
        self.assertEqual(actual,deck.replace('.t99)', '.t1)'))
        self.assertIn('V(Q0)',actual)

    def test_missing_node_or_missing_original_observation_is_rejected(self):
        deck,model=self.fixture()
        for d,m in [(deck,model.replace('__CT.t1','__OTHER.t1')),(deck.replace('V(XDR:openlvds_receiver_core__PP.t99)',''),model)]:
            with self.assertRaises(ValueError):restore.receiver_probes(d,m)

    def test_short_or_nonfinite_data_cannot_admit_long_diagnostic(self):
        w=np.column_stack([np.linspace(0,12e-9,13),np.ones(13)])
        self.assertTrue(restore.complete(['time','v(q)'],w,12e-9))
        self.assertFalse(restore.complete(['time','v(q)'],w,188.049e-9))
        for bad in [w[:-1],w[::-1],w.copy()]:
            if len(bad)==len(w) and bad[0,0]==0:bad[3,1]=np.nan
            self.assertFalse(restore.complete(['time','v(q)'],bad,12e-9))

    def test_diagnostics_in_other_namespaces_cannot_restore_or_run(self):
        with self.assertRaises(ValueError):restore.prepare(Path('/tmp/line'),Path('/tmp/receiver'))
        with self.assertRaises(ValueError):restore.run(Path('/tmp/receiver'))
        with self.assertRaises(ValueError):restore.followup(Path('/tmp/receiver'))

    def test_only_exact_live_line_owner_can_prepare_resource_handoff(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(restore,'ROOT',Path(tmp)):
            line=Path(tmp)/'build/diagnostics/channel_model_isolation/test'
            screen=Path(tmp)/'build/diagnostics/receiver_spec_screen/test'
            for live in [dict(MainPID='0',ActiveState='inactive',ExecStart=''),
                         dict(MainPID='42',ActiveState='active',ExecStart='scripts/isolate_channel_model.py run build/diagnostics/channel_model_isolation/other')]:
                with patch.object(restore,'owner',return_value=live):
                    with self.assertRaisesRegex(ValueError,'exact live'):restore.prepare_followup(line,screen,'unit')


if __name__=='__main__':unittest.main()
