from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pfd_control_protocol as protocol


class PFDControlProtocol(unittest.TestCase):
    def deck(self,clocks='REF FDB'):
        return f'fixture\nVRST RST 0 PWL(0 0 2n 0 2.1n 1.8)\nXP {clocks} RST VDDD UP DN VDDD 0 lvds_pfd\n.tran 5p 160n 0 20p\n.print tran V(UP) V(DN) V(REF) V(FDB)\n.end\n'

    def wave(self):
        t=np.arange(160001)*1e-12
        rst=np.interp(t*1e9,[0,2,2.02,30.2,30.22,35.2,35.22,160],[0,0,1.8,1.8,0,0,1.8,1.8])
        en=np.interp(t*1e9,[0,10.2,10.22,15.2,15.22,25.2,25.22,160],[0,0,1.8,1.8,0,0,1.8,1.8])
        clk=.9+.9*np.sin(2*np.pi*400e6*t)
        output=clk*((rst>1.44)&(en>1.44))
        wave=np.column_stack([np.arange(len(t)),t,rst,en,output,output,clk,clk])
        h={f'V({n})':i for i,n in enumerate(['RST','ENABLE','UP','DN','REF','FDB'],start=2)}
        return wave,h

    def test_both_source_and_native_fixtures_get_explicit_observed_controls(self):
        for clocks in ('REF FDB','REF_FAST FDB_FAST'):
            deck=protocol.apply(self.deck(clocks))
            self.assertIn('RST ENABLE UP DN',deck);self.assertIn(protocol.RESET,deck);self.assertIn(protocol.ENABLE,deck)
            self.assertIn('V(RST) V(ENABLE)',deck);self.assertIn('.tran 5p 160n 0 20p',deck)
            with self.assertRaises(ValueError):protocol.apply(deck)

    def test_timing_or_unknown_pfd_interface_cannot_be_rewritten(self):
        for deck in [self.deck().replace('160n','80n'),self.deck('UNKNOWN FDB'),self.deck().replace('lvds_pfd','other_pfd')]:
            with self.assertRaises(ValueError):protocol.apply(deck)

    def test_asserted_controls_clear_both_outputs_with_both_clocks_running(self):
        wave,h=self.wave();r=protocol.measure(wave,h,400)
        self.assertTrue(r['passed']);self.assertEqual(len(r['windows']),3)
        self.assertTrue(all(w['up_max_v']==0 and w['dn_max_v']==0 for w in r['windows']))

    def test_wrong_control_edges_live_output_and_stopped_clock_fail(self):
        wave,h=self.wave()
        for change in ('edge','UP','clock','release'):
            bad=wave.copy()
            if change=='edge':bad[:,h['V(ENABLE)']]=np.interp(bad[:,1]-50e-12,wave[:,1],wave[:,h['V(ENABLE)']])
            if change=='UP':bad[(bad[:,1]>18e-9)&(bad[:,1]<24e-9),h['V(UP)']]=.5
            if change=='clock':bad[(bad[:,1]>15e-9)&(bad[:,1]<26e-9),h['V(FDB)']]=0
            if change=='release':bad[bad[:,1]>120e-9,h['V(RST)']]=0
            with self.subTest(change=change):self.assertFalse(protocol.measure(bad,h,400)['passed'])

    def test_partial_waveform_and_missing_observations_fail(self):
        wave,h=self.wave()
        with self.assertRaises(ValueError):protocol.measure(wave[:10000],h,400)
        with self.assertRaises(ValueError):protocol.measure(wave,h,400,())
