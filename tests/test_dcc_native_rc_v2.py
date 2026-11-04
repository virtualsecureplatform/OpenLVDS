# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import re
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcc_native_rc_v3 as pilot


class NativeDccPilotTests(unittest.TestCase):
    spec=dict(process='ss',temperature=40,mhz=410,load_ff=100,slew0_ps=20,slew180_ps=250,duty=.3)
    info=dict(ports=['VGND','VPWR','clock_out','phase0','phase180','reset_n'])
    text='.subckt dut VGND VPWR clock_out phase0 phase180 reset_n\nX0 clock_out phase0 VGND VGND sky130_fd_pr__special_nfet_01v8 w=.36 l=.15\n.ends dut\n'

    def test_source_crossings_compensate_unequal_slew_and_release_on_own_high(self):
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            deck=pilot.fixture(Path('/pilot'),self.spec,self.info,self.text)
        pulses={m[1]:list(map(float,m[2].split())) for m in re.finditer(r'(?m)^V(P0|P180) \S+ 0 PULSE\(0 1.8 ([^)]*)\)',deck.replace('n',''))}
        a,b=pulses['P0'],pulses['P180'];period=1000/self.spec['mhz']
        self.assertAlmostEqual((b[0]+b[1]/2)-(a[0]+a[1]/2),period/2)
        self.assertIn('XD 0 VDD Q P0 P180 RESET_N '+pilot.NAME,deck)
        self.assertIn('CQ Q 0 100f',deck)
        self.assertIn('V(Q) V(VDD)',deck)
        self.assertNotIn('special_nfet_01v8 d g s b',deck)

    def wave(self,complement=False,missing=False,overstress=False):
        period=1e6/self.spec['mhz'];t=np.arange(0,2000+22*period+1,.5);p0=np.zeros(len(t));p1=p0.copy()
        source=[]
        for phase,v,offset in [('P0',p0,0),('P180',p1,period/2)]:
            for i in range(23):
                edge=2000+offset+i*period
                v[(t>=edge)&(t<edge+period*.3)]=1.8
                source.append((edge,phase))
        release=2000+3*period+150;reset=np.where(t>=release,1.8,0)
        q=np.full(len(t),1.8);events=np.zeros(len(t))
        for i,(edge,phase) in enumerate(sorted((e,p) for e,p in source if e>release)):
            if missing and i==7:continue
            events[(t>=edge+50)&(t<edge+150)]=1.8
            q[t>=edge+200]=1.8 if phase=='P0' else 0
        if complement:q=1.8-q
        if overstress:q[100]=2.1
        values={'p0':p0,'p180':p1,'reset_n':reset,'q':q,'vdd':np.full(len(t),1.8),'xd.combine.x':events}
        names=['time']+['v('+n+')' for n in values]
        return names,np.column_stack([t/1e12,*values.values()])

    def analyze(self,**kw):
        with patch.object(pilot,'read_raw',return_value=self.wave(**kw)):
            return pilot.analyze(Path('/fixture'),self.spec,self.info,self.text)

    def test_phase0_rising_polarity_and_one_event_per_source_are_required(self):
        result=self.analyze()
        self.assertTrue(result['event_integrity_passed']);self.assertTrue(result['phase0_delivery_passed'])
        self.assertTrue(result['half_cycle_passed']);self.assertTrue(result['terminal_screen_passed'])
        self.assertFalse(result['qualified_phy'])
        self.assertFalse(self.analyze(complement=True)['phase0_delivery_passed'])
        self.assertFalse(self.analyze(missing=True)['event_integrity_passed'])

    def test_terminal_overshoot_is_not_hidden_by_clean_steady_clock(self):
        result=self.analyze(overstress=True)
        self.assertFalse(result['terminal_screen_passed'])
        self.assertAlmostEqual(result['terminal_abs_peak_v'],2.1)

    def test_native_tie_resistors_are_preserved_and_unknown_devices_rejected(self):
        self.assertEqual(pilot.terminals(self.text+'Xtie a b sky130_fd_pr__res_generic_po w=.48 l=.5\n'),
                         [['clock_out','phase0','VGND','VGND']])
        with self.assertRaisesRegex(ValueError,'Unexpected extracted'):
            pilot.terminals(self.text+'Xunknown a b c d imaginary_device w=1 l=1\n')


if __name__=='__main__':unittest.main()
