# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from harden_dcc_inv8_300_v1 import retained


class DccPhysicalTopology(unittest.TestCase):
    def setUp(self):
        self.text=(Path(__file__).resolve().parents[1]/'sky130/v3/openlvds_dcc_inv8_300.v').read_text()

    def test_inv8_exact_feedback_and_reset_topology(self):
        self.assertTrue(retained(self.text))
        self.assertFalse(retained(self.text.replace('inv_8 output_drive','inv_4 output_drive')))
        self.assertFalse(retained(self.text.replace('.D(feedback)','.D(high)')))
        self.assertFalse(retained(self.text.replace('.RESET_B(breset)','.RESET_B(reset_n)')))
        self.assertFalse(retained(self.text.replace('.B1(bclk_n)','.B1(aclk_n)')))


if __name__=='__main__':unittest.main()
