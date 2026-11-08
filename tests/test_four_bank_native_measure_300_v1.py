# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import four_bank_native_measure_300_v1 as p
from dcdl_uniform_tree_v3 import encode
import test_two_bank_native_measure_300_v1 as fixtures


class FourSectionMeasureTests(unittest.TestCase):
    def fixture(self,folder,*,delays=(700,700,700,700),bad_gate=False,stress=False):
        helper=fixtures.RelativeTransportTests();helper.setUp();t=helper.t
        values={'time':t*1e-12,'v(vdd)':np.full(len(t),1.8),'v(in)':helper.wave()}
        obs={};total=0
        for k,delay in enumerate(delays):
            total+=delay;output='OUT' if k==0 else f'B{k}_OUT'
            inp='IN' if k==0 else 'OUT' if k==1 else f'B{k-1}_OUT'
            prefix='' if k==0 else f'B{k}_';gate=f'gate{k}'
            values['v('+output.lower()+')']=helper.wave(total)
            values['v('+gate+')']=np.zeros(len(t))
            if k==2 and bad_gate:values['v('+gate+')'][0:]=1.8
            if k==3 and stress:values['v('+gate+')'][0]=2.1
            for pin,v in encode(0,0).items():values['v('+prefix.lower()+pin.lower()+')']=np.full(len(t),1.8*v)
            obs[f'section{k}']=dict(devices=[dict(name=f'M{k}',terminals=[inp,gate,output,'0'],limit_v=1.95)],
                controls=[dict(node=gate,control='fine0')],programming_gates=[dict(device=f'M{k}',gate_node=gate,control='fine0',kind='fine')])
            if k:obs[f'section{k}'].update(input_node=inp,output_node=output,coarse=0,fine=0)
        names=list(values);data=np.column_stack(list(values.values()))
        header=('Title: synthetic four-section reader test\nFlags: real\n'
                f'No. Variables: {len(names)}\nNo. Points: {len(t)}\nVariables:\n'
                +''.join(f'\t{k}\t{n}\t'+('time' if k==0 else 'voltage')+'\n' for k,n in enumerate(names))+'Binary:\n')
        (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
        return obs,dict(helper.s,stop_ns=40)

    def test_independent_readers_and_relative_section_delays(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);obs,s=self.fixture(folder)
            a=p.measure(folder,obs,s);b=p.measure(folder,obs,s,independent_reader=True)
            self.assertTrue(a['four_section_transport_passed']);self.assertTrue(b['four_section_transport_passed'])
            for label,row in a['sections'].items():
                other=b['sections'][label]
                for edge in ('rise','fall'):
                    np.testing.assert_allclose(row['timing']['edge_delays_ps'][edge],700,atol=1e-6)
                    np.testing.assert_allclose(row['timing']['edge_delays_ps'][edge],other['timing']['edge_delays_ps'][edge],atol=1e-6)
                self.assertEqual(row['bank_screen_passed'],other['bank_screen_passed'])
            self.assertFalse(a['qualified_phy']);self.assertFalse(a['detector_dcc_fanout_qualified'])

    def test_late_section_failures_are_retained(self):
        for changes,key in ((dict(delays=(700,700,900,700)),'zero_code_quarter_passed'),
                            (dict(bad_gate=True),'control_settling_passed'),
                            (dict(stress=True),'terminal_screen_passed')):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);obs,s=self.fixture(folder,**changes)
                for independent in (False,True):
                    r=p.measure(folder,obs,s,independent_reader=independent)
                    self.assertFalse(r['four_section_transport_passed'])
                    row=r['sections']['section3' if 'stress' in changes else 'section2']
                    self.assertFalse(row['timing'][key] if key=='zero_code_quarter_passed' else row[key])

    def test_mismatched_section_wiring_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);obs,s=self.fixture(folder);obs['section2']['input_node']='OUT'
            with self.assertRaises(ValueError):p.measure(folder,obs,s)
            obs,s=self.fixture(folder)
            obs['section2']['devices'][0]['name']=obs['section1']['devices'][0]['name']
            with self.assertRaisesRegex(ValueError,'disjoint'):p.measure(folder,obs,s)
