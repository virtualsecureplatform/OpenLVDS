# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continuous_clock_conditioner_v2 as circuit
import probe_continuous_clock_conditioner_v2 as pilot


class ContinuousConditionerTests(unittest.TestCase):
    def test_real_clock_and_monitor_drivers_have_native_constant_loading(self):
        lib='.subckt sky130_fd_sc_hd__buf_8 A VGND VNB VPB VPWR X\nX0 X A private VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends\n'
        text=circuit.source(lib)
        self.assertEqual(text.count('XFIXED'),4);self.assertEqual(text.count('w=4 l=4'),4)
        self.assertEqual(text.count('XPRIVATE'),4)
        self.assertIn('Xclean0__X0 P0 F0 clean0__private VGND',text)
        self.assertIn('Xmonitor0__X0 MON0 P0 monitor0__private VGND',text)
        devices=circuit.mapped_mos(text,dict(P0='P0',F0='F0',VGND='0'),'XC')
        self.assertEqual(len(devices),4);self.assertEqual(devices[0]['limit_v'],1.95)
        with self.assertRaisesRegex(ValueError,'voltage domain'):
            circuit.mapped_mos('Xbad a b c d sky130_fd_pr__nfet_unknown w=1 l=1',{},'X')

    def waveform(self,missing=False,overshoot=False,vcm=.9):
        period=1e6/410;start=22000;stop=start+22*period;t=np.arange(0,stop+1,.5)
        def clock(origin):return np.where((t>=origin)&((t-origin)%period<.3*period),1.8,0)
        p0=clock(start+100)
        if overshoot:p0[100]=2.1
        values={'r0':clock(start),'r180':clock(start+period/2),'p0':p0,
                'p180':np.zeros(len(t)) if missing else clock(start+period/2+102),'xf.vcm':np.full(len(t),vcm)}
        return ['time',*['v('+n+')' for n in values]],np.column_stack([t/1e12,*values.values()])

    def measure(self,**options):
        task=dict(spec=dict(mhz=410));devices=[dict(name='test',model='sky130_fd_pr__nfet_01v8',limit_v=1.95,terminals=['P0','R0','0','0'])]
        with patch.object(pilot,'read_raw',return_value=self.waveform(**options)):
            return pilot.measure(Path('/fixture'),task,devices)

    def test_actual_crossing_latency_and_missing_clock_detection(self):
        result=self.measure();self.assertTrue(result['clock_conditioning_feasibility_passed'])
        self.assertLessEqual(result['maximum_half_spacing_error_ps'],3)
        self.assertTrue(result['dcc_held_in_reset']);self.assertFalse(result['qualified_phy'])
        self.assertFalse(self.measure(missing=True)['clock_event_integrity_passed'])

    def test_full_trace_stress_and_common_mode_cannot_be_hidden_by_steady_edges(self):
        self.assertFalse(self.measure(overshoot=True)['terminal_screen_passed'])
        self.assertFalse(self.measure(vcm=.92)['common_mode_passed'])


if __name__=='__main__':unittest.main()
