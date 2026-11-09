# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_inv8_output_300_v1 as p
import dcc_inv8_fixture_300_v1 as wiring


class DCCOutputDriveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent=p.source.ROOT/'build/diagnostics/dcc_source_300_v1/1a4f4e8eabb896e4'
        cls.cells=(cls.parent/'cells.spice').read_text();cls.hold=(cls.parent/'hold1.spice').read_text()
        cls.pdk=(Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice').read_text()

    def test_only_output_instance_changes_and_all_other_native_devices_preserved(self):
        cells,hold=p.transform(self.cells,self.hold,self.pdk)
        self.assertEqual(hold.replace(p.NEW,p.OLD),self.hold)
        before=p.baseline.inventory.native.definitions(self.cells);after=p.baseline.inventory.native.definitions(cells)
        for name,d in before.items():self.assertEqual(after[name],d)
        self.assertEqual(set(after)-set(before),{p.NEW})
        self.assertEqual(after[p.NEW],p.baseline.inventory.native.definitions(self.pdk)[p.NEW])
        obs=wiring.observations(cells+'\n'+hold);self.assertEqual(len(obs['devices']),144);self.assertEqual(len(obs['passive_resistors']),2)
        for s in wiring.waveform.specifications()[:4]:
            deck,actual=wiring.fixture(self.parent/'unused-inv8-pilot',s,cells+'\n'+hold)
            _,names=wiring.translate(deck);self.assertEqual(actual,obs)
            for d in actual['devices']:
                for n in d['terminals']:
                    if n!='0':self.assertIn('v('+n.replace(':','.').lower()+')',names)
            self.assertIn('CQ Q 0 20f',deck)

    def test_changed_hold_or_missing_pdk_driver_rejected(self):
        with self.assertRaises(ValueError):p.transform(self.cells,self.hold.replace('Xaff ','Xchanged ',1),self.pdk)
        with self.assertRaisesRegex(ValueError,'exact PDK'):p.transform(self.cells,self.hold,self.pdk.replace(p.NEW,'wrong_cell'))
