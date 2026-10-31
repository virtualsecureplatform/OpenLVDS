# SPDX-License-Identifier: GPL-3.0-only
from bisect import bisect_right
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_rx_burst as burst


class NativeBurstContract(unittest.TestCase):
    ports='VGND VPWR clk data[0] data[1] reset_n serial valid'.split()

    def test_stimulus_samples_match_every_expected_word_at_stressed_edges(self):
        for spec in burst.conditions():
            body,timing=burst.fixture(spec,self.ports)
            self.assertIn('C0 Q0 0 20f',body)
            self.assertEqual(len(timing['witnesses']),32)
            events=timing['serial_events'];times=[e['time_ns'] for e in events]
            for n,witness in enumerate(timing['witnesses'],burst.WARMUP):
                sampled=[]
                for edge in [timing['rising_ns'][n],timing['falling_ns'][n]]:
                    index=bisect_right(times,edge)-1;sampled.append(events[index]['value'])
                    self.assertGreater(edge-times[index],.2)
                    self.assertGreater(times[index+1]-edge,.2)
                self.assertEqual(sampled,witness['expected'])
                self.assertEqual(witness['publication_ns'],timing['rising_ns'][n+1])
            period=1000/spec['mhz']
            for n,(rise,fall) in enumerate(zip(timing['rising_ns'],timing['falling_ns'])):
                self.assertLessEqual(abs(rise-(5+n*period)),.050001)
                self.assertLessEqual(abs(fall-(5+(n+spec['duty'])*period)),.050001)

    def test_wrong_word_invalid_and_incomplete_traces_cannot_pass(self):
        _,timing=burst.fixture(burst.conditions()[0],self.ports)
        t=np.linspace(0,timing['stop_ns']*1e-9,120000)
        q0=np.zeros(len(t));q1=q0.copy();valid=q0.copy()
        for witness in timing['witnesses']:
            mask=(t>(witness['publication_ns']+.6)*1e-9)&(t<(witness['publication_ns']+1.2)*1e-9)
            q0[mask]=witness['expected'][0]*1.8;q1[mask]=witness['expected'][1]*1.8;valid[mask]=1.8
        wave=np.column_stack([np.arange(len(t)),t,q0,q1,valid]);header={'V(Q0)':2,'V(Q1)':3,'V(VALID)':4}
        report=burst.measure(wave,header,timing)
        self.assertTrue(report['passed']);self.assertEqual(report['bits'],64)
        bad=wave.copy();witness=timing['witnesses'][3]
        mask=(t>(witness['publication_ns']+.75)*1e-9)&(t<(witness['publication_ns']+1.10)*1e-9)
        bad[mask,2]=1.8-bad[mask,2]
        self.assertFalse(burst.measure(bad,header,timing)['passed'])
        bad=wave.copy();bad[:,4]=0
        self.assertFalse(burst.measure(bad,header,timing)['passed'])
        with self.assertRaisesRegex(ValueError,'Incomplete'):burst.measure(wave[:-1000],header,timing)
