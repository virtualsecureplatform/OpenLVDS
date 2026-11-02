# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_driver_gate_taper as probe
from driver_current_variant import source_variant


class TaperSourceExperiments(unittest.TestCase):
    def waveform(self):
        t=np.linspace(0,80e-9,801);names=['D','P','N','XD:XCORE:DP','XD:XCORE:DN','XD:XCORE:TOP','XD:XCORE:BOT','XD:XCORE:SINK',*probe.EXTRA]
        w=np.column_stack([np.arange(len(t)),t,*[np.full(len(t),1.2) for n in names]])
        return w,{'V('+n+')':i+2 for i,n in enumerate(names)}

    def test_real_helper_internal_probes_and_supply_saves_are_valid(self):
        source=source_variant((probe.ROOT/'analog/openlvds.spice').read_text());source=probe.circuit.transform(source,'taper_16_32_64')
        deck='Taper\n.include "/old/source.spice"\nXD D P N VREF IREF VDDIO VDDD 0 openlvds_driver\n.tran 1p 80n 0 1p\n.print tran V(D) V(P) V(N)\n.end\n'
        actual=probe.fixture(deck,Path('/old'),Path('/new'),source)
        self.assertIn('.save i(VIO) i(VDIG)\n',actual)
        self.assertIn('.include "/new/source.spice"',actual)
        for name in probe.EXTRA:self.assertIn('V('+name+')',actual)
        with self.assertRaises(ValueError):probe.fixture(deck.replace('80n','12n'),Path('/old'),Path('/new'),source)

    def test_added_mos_stress_and_supply_power_use_real_saved_currents(self):
        w,h=self.waveform();raw=np.column_stack([w[:,1],np.full(len(w),-.002),np.full(len(w),-.001)])
        with patch.object(probe,'read_wave',return_value=(w,h)),patch.object(probe,'read_raw',return_value=(['time','i(vio)','i(vdig)'],raw)),patch.object(probe.reference,'measure',return_value={}):
            result=probe.measure(Path('/tmp/fixture'),'taper_16_32_64')
        self.assertAlmostEqual(result['mean_supply_power_w']['io'],.0066)
        self.assertAlmostEqual(result['mean_supply_power_w']['digital'],.0018)
        stress=result['added_mos_stress'];self.assertEqual(len(stress),12)
        self.assertEqual(sum(r['parallel_devices'] for r in stress),28)
        for row in stress:
            self.assertAlmostEqual(row['max_abs_vgs'],2.1 if row['polarity']=='p' else 1.2)
            self.assertAlmostEqual(row['max_abs_vgd'],0)
            self.assertAlmostEqual(row['max_abs_vbs'],0)
        with patch.object(probe,'read_wave',return_value=(w,h)),patch.object(probe,'read_raw',return_value=(['time','i(vdig)'],raw[:,[0,2]])),patch.object(probe.reference,'measure',return_value={}):
            with self.assertRaisesRegex(ValueError,'Missing real supply'):probe.measure(Path('/tmp/fixture'),'taper_16_32_64')

    def test_unrelated_contexts_cannot_admit_or_run(self):
        with self.assertRaises(ValueError):probe.prerequisites(Path('/tmp/other'))
        with self.assertRaises(ValueError):probe.run(Path('/tmp/other'))


if __name__=='__main__':unittest.main()
