# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_driver_compact_components as components


class CompactLongComponentFixtures(unittest.TestCase):
    MODEL='''.subckt openlvds_driver D OUTP OUTN VREF IREF VDDIO VDDD VSS
XCORE D OUTP OUTN VREF IREF IREF VDDIO VDDD VSS core
.ends openlvds_driver
.subckt core D OUTP OUTN VREF PB NB VDDIO VDDD VSS
R0 SINK TOP 10
R1 DP DN 10
.ends core
'''
    DECK='''.include "/old/source.spice"
VIO VDDIO 0 3.3
VDIG VDDD 0 1.8
VD D 0 PWL(0n 0 1900n 1.8)
XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver
RT P N 100
CP P 0 2p
CN N 0 2p
.tran 5p 2540n 0 1n
.print tran V(D) V(P) V(N) V(XD:XCORE:SINK) V(XD:XCORE:TOP) V(XD:XCORE:DP) V(XD:XCORE:DN)
.end
'''
    def test_original_stimulus_accuracy_load_and_order_retained(self):
        deck,rows=components.fixture(self.DECK,Path('/old'),Path('/new'),self.MODEL,'schematic',{})
        self.assertEqual(rows,[])
        self.assertEqual(deck,self.DECK.replace('/old/source.spice','/new/source.spice').replace(
            '.end','.save i(VIO) i(VDIG)\n.end'))
        for changed in [self.DECK.replace('2540n','2000n'),self.DECK.replace('0 1n','0 2n'),
                        self.DECK.replace('V(XD:XCORE:DP)','V(XD:XCORE:BOT)')]:
            with self.assertRaises(ValueError): components.fixture(changed,Path('/old'),Path('/new'),self.MODEL,'schematic',{})

    def test_incomplete_pilot_cannot_assemble_or_prepare_components(self):
        with patch.object(components.qualification,'pilot_ready',side_effect=ValueError('incomplete')),patch.object(components.assembly,'assemble') as assemble:
            with self.assertRaises(ValueError): components.prepare(Path('/pilot'),Path('/assembly'))
            assemble.assert_not_called()
