# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits,flatten

class DeviceTerminals(unittest.TestCase):
    def test_extra_mos_terminal_is_rejected(self):
        with self.assertRaises(ValueError):
            circuits('.subckt top A B C D\nX1 A B C D D sky130_fd_pr__nfet_01v8 w=4 l=.15\n.ends top\n')
    def test_missing_hierarchical_pin_is_rejected(self):
        with self.assertRaises(ValueError):
            circuits('.subckt child A B\n.ends child\n.subckt top A B\nX1 A child\n.ends top\n')

    def test_analog_macros_have_no_dangling_internal_terminals(self):
        source=Path(__file__).resolve().parents[1]/'analog/openlvds.spice'
        definitions=circuits(source.read_text())
        for top in ['openlvds_driver_core','openlvds_receiver_core','openlvds_delay_line','openlvds_dll_analog','lvds_bias']:
            ports,devices=flatten(definitions,top)
            counts=Counter(node for device in devices for node in device['nodes'])
            self.assertEqual([node for node,count in counts.items() if count==1 and node not in ports],[],top)

if __name__=='__main__':unittest.main()
