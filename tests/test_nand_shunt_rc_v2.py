# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_nand_shunt_rc_v2 as pilot


class NativeGatePilotTests(unittest.TestCase):
    spec=dict(macro='gate',process='ss',temperature=40,mhz=410,slew_ps=20,load_ff=20,swap=False)

    def waveform(self,missing=False,stress=False):
        t=np.arange(0,2000+9e6/410+1,.5);p=1e6/410
        a=(t>=2000)&((t-2000)%p<p/2);b=(t>=2000+p/4)&((t-2000-p/4)%p<p/2)
        y=np.full(len(t),1.8);target=~(a&b)
        for n in np.flatnonzero(target[1:]!=target[:-1])+1:y[t>=t[n]+100]=1.8 if target[n] else 0
        if missing:y[:]=1.8
        if stress:y[10]=2.1
        return ['time','v(a)','v(b)','v(y)'],np.column_stack([t/1e12,a*1.8,b*1.8,y])

    def test_event_truth_and_terminal_failures_are_independent(self):
        devices=[dict(name='XG:test',terminals=['Y','A','0','0'],limit_v=1.95)]
        for kwargs,event,health in [({},True,True),({'missing':True},False,True),({'stress':True},True,False)]:
            with patch.object(pilot,'read_raw',return_value=self.waveform(**kwargs)):
                r=pilot.analyze(Path('/fixture'),self.spec,devices)
            self.assertEqual(r['event_integrity_passed'],event);self.assertEqual(r['terminal_screen_passed'],health)
            self.assertFalse(r['qualified_phy'])

    def test_rc_port_order_and_quarter_period_pin_swap(self):
        gate=dict(info=dict(ports=['Y','VGND','B','A','VPWR']))
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            a=pilot.fixture(Path('/fixture'),self.spec,gate,[])
            b=pilot.fixture(Path('/fixture'),{**self.spec,'swap':True},gate,[])
        self.assertIn('XG Y 0 B A VDD gate',a);self.assertNotEqual(a,b)
        self.assertNotIn('Bdelay',a);self.assertNotIn('.ic',a)


if __name__=='__main__':unittest.main()
