# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rx_buffered_policy import retained


class RXBufferedPolicy(unittest.TestCase):
    def source(self):return (Path(__file__).resolve().parents[1]/'rtl/experiments/openlvds_ddr_rx_buffer4.v').read_text()

    def test_declared_buffered_candidate_keeps_direct_sampler_and_valid_driver(self):
        self.assertTrue(retained(self.source()))

    def test_wrong_drive_strength_clock_and_duplicate_driver_are_rejected(self):
        s=self.source()
        for changed in [s.replace('__buf_4','__buf_1',1),s.replace('.CLK(clk_n)','.CLK(clk)'),
            s.replace('.D(serial)','.D(other)'),s+'\nsky130_fd_sc_hd__buf_4 unwanted(.A(other),.X(data[0]));']:
            self.assertFalse(retained(changed))
