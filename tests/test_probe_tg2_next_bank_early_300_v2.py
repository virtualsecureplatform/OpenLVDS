# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_tg2_next_bank_early_300_v2 as p


class LoadedPilotGates(unittest.TestCase):
    def rows(self):
        return [dict(task=dict(id=str(k),next_fine=f,centered=c),error=None,
                     result=dict(two_bank_zero_pilot_passed=True))
                for k,(f,c) in enumerate(((0,True),(31,True),(0,False),(31,False)))]

    def test_pending_source_refuses_before_binding_or_capture(self):
        with tempfile.TemporaryDirectory(dir=p.ROOT/'build') as folder:
            parent=Path(folder)
            with patch.object(p,'PARENT',parent),patch.object(p.SOURCE,'bound') as bound, \
                    patch.object(p.materials,'check') as check:
                with self.assertRaisesRegex(ValueError,'source point is still pending: 0'):
                    p.prepare([parent/'zero-proof',parent/'fine-proof'])
                bound.assert_not_called();check.assert_not_called()
            self.assertEqual(list(parent.iterdir()),[])

    def test_centered_material_order_preserves_both_fresh_references(self):
        material=json.loads((p.MATERIAL/'manifest.json').read_text())
        selected=[material['tasks'][int(n)] for n in p.MATERIAL_ORDER]
        self.assertEqual([t['centered'] for t in selected],[True,True,False,False])
        self.assertEqual([t['next_fine'] for t in selected],[0,31,0,31])
        self.assertEqual(len({t['id'] for t in selected}),4)
        for unshifted,centered in ((2,0),(3,1)):
            a=selected[unshifted];b=selected[centered]
            card=p.SOURCE.numerical_trial.CARD+'\n'
            original=(p.MATERIAL/a['id']/'bench.cir').read_text()
            shifted=(p.MATERIAL/b['id']/'bench.cir').read_text()
            self.assertEqual(shifted.replace(card,'',1),original)

    def test_all_loaded_cases_and_both_pairs_required(self):
        rows=self.rows();pairs={'0':dict(passed=True),'31':dict(passed=True)}
        self.assertTrue(p.pilot_passed(rows,pairs))
        for missing in (rows[:2],[],rows[::-1]):
            with self.assertRaisesRegex(ValueError,'all four'):
                p.pilot_passed(missing,pairs)
        with self.assertRaisesRegex(ValueError,'both fresh'):
            p.pilot_passed(rows,{'0':dict(passed=True)})
        for k in range(4):
            failed=deepcopy(rows);failed[k]['result']['two_bank_zero_pilot_passed']=False
            self.assertFalse(p.pilot_passed(failed,pairs))
        bad=deepcopy(rows);bad[2].update(error='native failure',result=None)
        self.assertFalse(p.pilot_passed(bad,pairs))
        self.assertFalse(p.pilot_passed(rows,{'0':dict(passed=True),'31':dict(passed=False)}))

    def native_pair(self,hidden_error=0,dc_error=0,gate_failure=False):
        t=np.arange(0,40001,dtype=float);v=np.zeros(len(t))
        for k in range(8):
            rise=2100+k*1e6/310;fall=rise+.5*1e6/310
            v+=1.8*np.minimum(np.clip((t-rise+50)/100,0,1),np.clip((fall+50-t)/100,0,1))
        names=['time','v(in)','v(out)','v(next_out)','v(hidden_terminal)']
        x=np.column_stack((t*1e-12,v,v,v,np.zeros(len(t))));y=x.copy()
        y[3000,-1]+=hidden_error;y[0,-1]+=dc_error
        bank=dict(bank_screen_passed=True,terminal_screen_passed=True,control_settling_passed=True,
                  timing=dict(stage_transport_passed=True,input_timing_stimulus_passed=None),
                  terminal_stress=[dict(passed=True)],controls=[dict(passed=True)],
                  programming_gates=[dict(passed=True)],external_controls=[dict(passed=True)])
        rows=[dict(error=None,result=dict(banks=dict(first=deepcopy(bank),next=deepcopy(bank)),fixed_supply_passed=True)) for k in range(2)]
        if gate_failure:rows[1]['result']['banks']['next']['programming_gates'][0]['passed']=False
        with patch.object(p,'validate',side_effect=[(names,x),(names,y)]):
            return p.numerical_pair(p.ROOT/'build/unused-loaded-parity',rows,0,1)

    def test_internal_voltages_and_dc_cannot_be_excluded_from_parity(self):
        self.assertTrue(self.native_pair()['passed'])
        self.assertFalse(self.native_pair(hidden_error=.003)['passed'])
        self.assertFalse(self.native_pair(dc_error=2e-9)['passed'])
        self.assertFalse(self.native_pair(gate_failure=True)['passed'])
