# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import tempfile
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_receiver_spec as admission
import observe_tx_isolation as observation
import continue_receiver_spec_components as followup


class SpecificationAdmission(unittest.TestCase):
    def test_unrelated_evidence_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'specification screen'):admission.recheck(Path('/tmp/legacy'),Path('/tmp/replay'))

    def test_original_component_gate_is_restored_after_error(self):
        original=admission.components.CODE,admission.components.replay_ready,admission.spice_slots.slot
        with self.assertRaisesRegex(RuntimeError,'controlled'):
            with admission.selection(Path('/screen'),Path('/replay')):
                self.assertIsNot(admission.components.replay_ready,original[1])
                self.assertIn('qualify_receiver_spec.py',admission.components.CODE)
                raise RuntimeError('controlled')
        self.assertEqual((admission.components.CODE,admission.components.replay_ready,admission.spice_slots.slot),original)


class TxRawCompletion(unittest.TestCase):
    def test_full_trace_can_complete_independently_of_export(self):
        w=np.column_stack([np.linspace(0,12e-9,13),np.zeros(13)])
        self.assertTrue(observation.trace_completion(['time','v(q)'],w))
        for bad in [w[:-1],w[::-1],w.copy()]:
            if len(bad)==len(w) and bad[0,0]==0:bad[3,1]=np.nan
            self.assertFalse(observation.trace_completion(['time','v(q)'],bad))


class SpecificationHandoff(unittest.TestCase):
    def test_dead_or_other_producer_cannot_launch_components(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(followup,'ROOT',Path(tmp)):
            screen=Path(tmp)/'build/diagnostics/receiver_spec_screen/test'
            states=[dict(MainPID='0',ActiveState='inactive',ExecStart=''),
                    dict(MainPID='42',ActiveState='active',ExecStart='scripts/receiver_spec_screen.py run build/diagnostics/receiver_spec_screen/other')]
            for state in states:
                with patch.object(followup,'owner',return_value=state):
                    with self.assertRaisesRegex(ValueError,'exact live'):followup.prepare(screen,'unit')

    def test_admission_and_handoff_reject_other_namespaces(self):
        with self.assertRaisesRegex(ValueError,'component matrix'):admission.run(Path('/tmp/legacy'))
        with self.assertRaisesRegex(ValueError,'specification handoff'):followup.run(Path('/tmp/legacy'))


if __name__=='__main__':unittest.main()
