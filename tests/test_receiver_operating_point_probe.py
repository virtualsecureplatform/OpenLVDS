# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_operating_point_probe as probe


class ReceiverOperatingProbe(unittest.TestCase):
    DECK='''Original static tt25
.include "/parent/source.spice"
.options device temp=25
.options timeint method=gear reltol=1e-4 abstol=1e-12
VIO VDDIO 0 3.3
VDIG VDDD 0 1.8
VREF VREF 0 1.2
IREF IREF 0 35u
VP P 0 PWL(0n 0 12n .1)
VN N 0 PWL(0n .1 12n 0)
XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver
CQ Q 0 100f
.tran 10p 144n 0 50p
.print tran V(P) V(N) V(Q)
.end
'''

    def test_operating_deck_retains_rails_reference_load_and_source_with_only_inputs_altered(self):
        points=[dict(p_v=0.,n_v=.1),dict(p_v=2.3,n_v=2.4)]
        result=probe.operating_deck(self.DECK,Path('/parent'),Path('/new'),points)
        for row in ['VIO VDDIO 0 3.3','VDIG VDDD 0 1.8','VREF VREF 0 1.2','IREF IREF 0 35u','CQ Q 0 100f',
                'XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver','.temp 25']:
            self.assertIn(row,result)
        self.assertEqual(result.count('\nop\n'),2)
        self.assertIn('let tail_vdsat = '+probe.TAIL+'[vdsat]',result)
        self.assertIn('.include "/new/source.spice"',result)
        self.assertNotIn('.tran ',result);self.assertNotIn('.print ',result)

    def test_changed_supply_or_missing_original_input_source_is_refused(self):
        for text in [self.DECK.replace('VDDIO 0 3.3','VDDIO 0 3.2'),self.DECK.replace('VP P 0','VP OTHER 0')]:
            with self.assertRaises(ValueError):probe.operating_deck(text,Path('/parent'),Path('/new'),[])

    def test_measures_model_parameters_and_rail_reference_power_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'point_0.raw').write_bytes(b'fixture')
            voltages=[0.,.1,0.,.67,.72,1.5,.7,.05,.8]
            names=['v('+n.replace(':','.').lower()+')' for n in probe.NODES]+['i(vio)','i(vdig)','i(vref)','tail_id','tail_gm','tail_gds','tail_vdsat']
            wave=np.array([voltages+[-.001,-.0001,-.0002,.0001,.001,.0001,.25]])
            expected={'V('+n+')':v for n,v in zip(probe.NODES,voltages)}
            point=dict(time_ns=10,p_v=0.,n_v=.1,expected=expected)
            with patch.object(probe,'read_raw',return_value=(names,wave)):
                result=probe.measure(folder,[point])[0]
                self.assertAlmostEqual(result['power']['rails_mw'],3.48)
                self.assertAlmostEqual(result['power']['reference_mw'],.24)
                self.assertEqual(result['tail']['vdsat'],.25)
                self.assertTrue(all(v==0 for v in result['voltage_differences_from_transient_v'].values()))
                wave[0,0]=2.3
                with self.assertRaisesRegex(ValueError,'input differs'):probe.measure(folder,[point])

    def test_missing_or_nonfinite_model_vectors_cannot_produce_measurements(self):
        with tempfile.TemporaryDirectory() as tmp:
            point=dict(time_ns=10,p_v=0.,n_v=.1,expected={})
            for names,wave in [(['v(p)'],np.array([[0.]])),(['v(p)'],np.array([[np.nan]]))]:
                with patch.object(probe,'read_raw',return_value=(names,wave)):
                    with self.assertRaises(ValueError):probe.measure(Path(tmp),[point])


if __name__=='__main__':unittest.main()
