# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_routed_dcdl_bank_v2 as pilot


class RoutedBankPilotTests(unittest.TestCase):
    def model(self):
        ports=['IN','OUT','VGND','VPWR',*[f'C{i}' for i in range(15)],*[f'E{i}' for i in range(31)]]
        return '.subckt bank '+' '.join(ports)+'\nX0 IN OUT VGND bulk.t0 sky130_fd_pr__nfet_01v8 w=1 l=.15\nR0 bulk.t0 VGND 1\nC0 OUT VGND 1f\n.ends\n'

    def waveform(self,folder,delay=100,bulk_peak=0):
        t=np.arange(0,20001,100,dtype=float)
        inp=np.where(((t>=2100)&(t<6100))|((t>=12100)&(t<16100)),1.8,0)
        out=np.interp(t-delay,t,inp,left=0,right=0)
        bulk=np.where(t==5000,bulk_peak,0)
        names=['time','v(in)','v(out)','v(vdd)','v(xd.bulk.t0)',*[f'v(c{i})' for i in range(15)],*[f'v(e{i})' for i in range(31)]]
        w=np.column_stack([t*1e-12,inp,out,np.full(len(t),1.8),bulk,*[np.zeros(len(t)) for _ in range(46)]])
        header=f'Flags: real\nNo. Variables: {len(names)}\nNo. Points: {len(t)}\nVariables:\n'
        header+=''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+w.astype('<f8').tobytes())

    def test_all_physical_bulk_terminals_are_saved_and_screened(self):
        _,_,mos=pilot.devices(self.model())
        self.assertEqual(mos[0]['terminals'],['IN','OUT','0','XD:bulk.t0'])
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.waveform(folder,bulk_peak=2)
            result=pilot.measure(folder,pilot.specifications()[0],mos)
            self.assertFalse(result['terminal_screen_passed']);self.assertFalse(result['native_pulse_passed'])
            self.assertAlmostEqual(result['samples'][0]['rise_delay_ps'],100)

    def test_absolute_delay_does_not_wrap_and_failed_quarter_headroom_is_retained(self):
        _,_,mos=pilot.devices(self.model())
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.waveform(folder,delay=700)
            result=pilot.measure(folder,pilot.specifications()[0],mos)
            self.assertFalse(result['minimum_below_fast_quarter'])
            self.assertTrue(result['native_pulse_passed'])
            self.assertAlmostEqual(result['samples'][0]['rise_delay_ps'],700)
            self.assertFalse(result['qualified_phy']);self.assertFalse(result['legal_code_table_admitted'])

    def test_fixture_uses_native_port_order_and_both_thermometer_banks(self):
        spec=dict(pilot.specifications()[0],coarse=1,fine=31)
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            text=pilot.fixture(Path('/pilot'),spec,self.model())
        self.assertIn('VC0 C0 0 1.8',text);self.assertIn('VC1 C1 0 0',text)
        self.assertIn('VE30 E30 0 1.8',text);self.assertIn('V(XD:bulk.t0)',text)
        self.assertIn('XD IN OUT 0 VDD C0 C1',text);self.assertIn('.tran 2p 20n 0 2p',text)
        with self.assertRaises(ValueError):pilot.devices(self.model().replace('nfet_01v8','nfet_g5v0d10v5'))


if __name__=='__main__':unittest.main()
