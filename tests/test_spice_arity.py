# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits

class DeviceTerminals(unittest.TestCase):
    def test_extra_mos_terminal_is_rejected(self):
        with self.assertRaises(ValueError):
            circuits('.subckt top A B C D\nX1 A B C D D sky130_fd_pr__nfet_01v8 w=4 l=.15\n.ends top\n')
    def test_missing_hierarchical_pin_is_rejected(self):
        with self.assertRaises(ValueError):
            circuits('.subckt child A B\n.ends child\n.subckt top A B\nX1 A child\n.ends top\n')

if __name__=='__main__':unittest.main()
