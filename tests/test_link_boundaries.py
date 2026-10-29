# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from simulate_link import analyze,word_stream


class LinkMeasurementBoundaries(unittest.TestCase):
    def fixture(self,received_swing=.22):
        t=np.arange(0,90e-9,5e-12);period=2.5e-9;start=10e-9
        board=1.2e-9;receiver=.8e-9;phase=period/4
        words=word_stream(20)
        def bits(at):
            index=np.floor((at-start)/period).astype(int)
            bit=((at-start)%period>=period/2).astype(int)
            result=np.array([(words[min(max(i,0),len(words)-1)]>>int(b))&1 for i,b in zip(index,bit)],float)
            result[index<0]=1-bit[index<0]
            result[index>=len(words)]=(words[-1]>>1)&1
            return result
        def analog(at):
            n=80
            return 2*np.convolve(bits(at),np.ones(n)/n,mode='full')[:len(t)]-1
        rx=analog(t-board);tx=analog(t)
        pin_clock=2*(((t-board-phase)%period)<period/2)-1
        tx_clock=2*(((t-phase)%period)<period/2)-1
        digital_clock=1.8*(((t-board-receiver-phase)%period)<period/2)
        digital_data=1.8*bits(t-board-receiver-.2e-9)
        previous=np.floor((t-start-board-receiver-phase)/period).astype(int)-1
        published=np.array([words[i] if 0<=i<len(words) else 0 for i in previous])
        wave=np.column_stack([np.arange(len(t)),t,1.2+received_swing/2*rx,1.2-received_swing/2*rx,
            1.2+.175*pin_clock,1.2-.175*pin_clock,digital_data,digital_clock,
            1.8*(published&1),1.8*((published>>1)&1),np.full(len(t),1.8),np.full(len(t),1.8),
            1.2+.175*tx,1.2-.175*tx,1.2+.175*tx_clock,1.2-.175*tx_clock])
        return wave,words,(start+np.arange(len(words))*period)*1e9,period*1e9

    def test_receiver_and_transmitter_limits_use_their_own_boundaries(self):
        result=analyze(*self.fixture())
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['checked_bits'],40)
        self.assertAlmostEqual(result['sampling_differential_min_v'],.22,places=6)
        self.assertGreater(result['setup_margin_ps'],200)
        self.assertGreater(result['hold_margin_ps'],200)
        self.assertTrue(all(x['passed'] for x in result['transmitter']))

    def test_loaded_tx_eye_is_diagnostic_but_rx_sensitivity_still_gates(self):
        args=list(self.fixture())
        wave=args[0].copy()
        for p,n in [(12,13),(14,15)]:
            wave[:,p]=1.2+(wave[:,p]-1.2)*.5
            wave[:,n]=1.2+(wave[:,n]-1.2)*.5
        args[0]=wave
        result=analyze(*args)
        self.assertTrue(result['passed'],result)
        self.assertTrue(all(not x['passed'] for x in result['transmitter']))
        self.assertTrue(all(x['qualification']=='diagnostic_loaded_eye' for x in result['transmitter']))

    def test_decoded_bits_do_not_override_insufficient_input_swing(self):
        result=analyze(*self.fixture(received_swing=.06))
        self.assertEqual(result['word_errors'],0)
        self.assertFalse(result['electrical_passed'])
        self.assertFalse(result['passed'])


if __name__=='__main__':unittest.main()
