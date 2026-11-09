# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_full_native_fixture_300_v3 as fixture
import dcc_full_native_measure_300_v3 as reader
import test_dcc_source_measure_300_v2 as synthetic
from replay_bank_300_v2 import same


class FullDCCNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent=fixture.waveform.previous.ROOT/'build/diagnostics/dcc_source_300_v1/1a4f4e8eabb896e4'
        cls.library='\n'.join((cls.parent/n).read_text() for n in ('cells.spice','hold1.spice'))
        cls.obs=fixture.observations(cls.library)

    def test_actual_finite_deck_preserves_every_nonobservation_line_and_saves_all_terminals(self):
        for s in fixture.waveform.specifications()[:4]:
            out=self.parent/'unused-full-dcc-test';original=fixture.waveform.fixture(out,s)
            text,obs=fixture.fixture(out,s,self.library);_,names=fixture.translate(text)
            keep=lambda x:[line for line in x.splitlines() if not line.startswith('.print tran ')]
            self.assertEqual(keep(text),keep(original));self.assertEqual(obs,self.obs)
            for d in obs['devices']+obs['passive_resistors']:
                for n in d['terminals']:
                    if n!='0':self.assertIn('v('+n.replace(':','.').lower()+')',names)
            self.assertIn('v(reset_n)',names)
        with self.assertRaisesRegex(ValueError,'Unsupported'):
            fixture.observations(self.library.replace('sky130_fd_pr__res_generic_po','unknown_resistor'))
        with self.assertRaisesRegex(ValueError,'interface'):
            fixture.observations(self.library.replace('P0 P180 RESET_N Q VDD VSS','P0 P180 Q RESET_N VDD VSS',1))

    def data(self):
        names,w,s=synthetic.CompleteDCCSourceTests().fixture();t=w[:,0]*1e12
        values={n:w[:,k] for k,n in enumerate(names)}
        values['v(reset_n)']=1.8*np.clip((t-1000)/20,0,1)
        for d in self.obs['devices']+self.obs['passive_resistors']:
            for n in d['terminals']:
                if n!='0':values.setdefault('v('+n.replace(':','.').lower()+')',np.zeros(len(t)))
        return list(values),np.column_stack(list(values.values())),s

    def test_full_startup_and_all_source_device_envelopes_agree_between_readers(self):
        names,w,s=self.data();a=reader.measure(names,w,s,self.obs);b=reader.measure(names,w,s,self.obs,independent=True)
        self.assertTrue(same(a,b));self.assertTrue(a['source_screen_passed']);self.assertEqual(len(a['terminal_stress']),136)
        self.assertFalse(a['qualified_phy']);self.assertFalse(a['complete_matrix_admitted'])

    def test_dc_internal_device_and_reset_failures_cannot_hide_behind_good_final_output(self):
        names,w,s=self.data()
        internal=next(n for d in self.obs['devices'] for n in d['terminals']
                      if n.startswith('XD:') and n.count(':')>=2)
        bad=w.copy();bad[0,names.index('v('+internal.replace(':','.').lower()+')')]=2.1
        for independent in (False,True):
            r=reader.measure(names,bad,s,self.obs,independent=independent)
            self.assertFalse(r['source_screen_passed']);self.assertFalse(r['native_terminal_stress_passed'])
        bad=w.copy();bad[0,names.index('v(reset_n)')]=.1
        r=reader.measure(names,bad,s,self.obs);self.assertFalse(r['reset_input_contract_passed']);self.assertFalse(r['source_screen_passed'])
        with self.assertRaisesRegex(ValueError,'Missing actual'):
            reader.measure([n+'bad' if n=='v(reset_n)' else n for n in names],w,s,self.obs)
