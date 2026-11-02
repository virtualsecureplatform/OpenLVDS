# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import isolate_tx_convergence as isolation


class TxIsolation(unittest.TestCase):
    def setUp(self):
        self.library='''.subckt openlvds_tx_core VGND VPWR
+ tx_serial forwarded_clock
R1 VGND VGND.t436 1
R2 VGND VGND.t435 1
R3 VGND VGND.t434 1
R4 VGND VGND.n5812 1
R5 VGND VGND.t522 1
R6 VPWR VPWR.t549 1
.ends openlvds_tx_core
'''
        self.deck='''Diagnostic
.lib "/pdk/models.spice" ss
.include "/parent/library.spice"
.options reltol=1e-4 abstol=1e-12
VDD VDDD 0 1.8
VIN INPUT 0 PWL(0 0 1n 1.8)
IREF 0 BIAS 35u
XTX 0 VDDD TXDATA TXCLOCK openlvds_tx_core
XRX TXDATA RXOUT receiver
RCHANNEL TXDATA RXOUT 100
.tran 20p 188.049n 0 1p
.print tran V(TXDATA)
.end
'''

    def test_tx_only_preserves_sources_and_accuracy_without_receiver_or_bias(self):
        result=isolation.fixture(self.deck,self.library,Path('/parent'),Path('/new'),True)
        for line in self.deck.splitlines():
            if line.startswith(('V','.options','.lib','XTX')):self.assertIn(line,result)
        for line in ['IREF','XRX','RCHANNEL']:self.assertNotIn(line,result)
        self.assertIn('CISO0 TXDATA 0 100f',result)
        self.assertIn('CISO1 TXCLOCK 0 100f',result)
        self.assertIn('.tran 1p 12n 0 1p',result)
        self.assertEqual(result.count('.end\n'),1)

    def test_coupled_keeps_loads_and_bias_and_adds_failed_cluster_probes(self):
        result=isolation.fixture(self.deck,self.library,Path('/parent'),Path('/new'),False)
        for line in self.deck.splitlines():
            if line.startswith(('IREF','XRX','RCHANNEL','V','.options','XTX')):self.assertIn(line,result)
        self.assertIn('V(XTX:VGND.t436)',result)
        self.assertIn('V(XTX:VPWR.t549)',result)
        self.assertEqual(result.count('.print tran'),1)

    def test_changed_time_policy_or_missing_probe_is_rejected(self):
        for deck,library in [(self.deck.replace('0 1p','0 20p'),self.library),
                             (self.deck,self.library.replace('VGND.t436','other'))]:
            with self.assertRaises(ValueError):isolation.fixture(deck,library,Path('/parent'),Path('/new'),True)

    def test_runner_rejects_unrelated_context_before_reading(self):
        with self.assertRaisesRegex(ValueError,'isolated TX'):isolation.run(Path('/tmp/unrelated'))


if __name__=='__main__':unittest.main()
