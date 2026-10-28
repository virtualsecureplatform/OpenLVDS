# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from physical_policy import tx_cells_retained


class NativeSerializerMapping(unittest.TestCase):
    def fixture(self):
        cells=[('xor2_1','rise_logic','.A(D0),.B(FALL),.X(RNEXT)'),
            ('xor2_1','fall_logic','.A(HELD),.B(RISE),.X(FNEXT)'),
            ('xor2_4','output_logic','.A(RISE),.B(FALL),.X(SERIAL)'),
            ('inv_4','falling_clock_14','.A(CLK),.Y(CLKN)'),
            ('dfrtp_4','rise_sample','.CLK(CLK),.D(RNEXT),.RESET_B(RST),.Q(RISE)'),
            ('dfrtp_4','held_sample','.CLK(CLK),.D(D1),.RESET_B(RST),.Q(HELD)'),
            ('dfrtp_4','fall_sample','.CLK(CLKN),.D(FNEXT),.RESET_B(RST),.Q(FALL)')]
        return '\n'.join(f'sky130_fd_sc_hd__{cell} \\{lane}/{name} ({pins});'
            for lane in ['data_launch','clock_launch'] for cell,name,pins in cells)

    def test_matched_native_cells_and_routed_clock_name_pass(self):
        self.assertTrue(tx_cells_retained(self.fixture()))

    def test_remapped_output_gate_is_rejected(self):
        self.assertFalse(tx_cells_retained(self.fixture().replace('xor2_4','nand2_4',1)))

    def test_wrong_output_operand_is_rejected(self):
        self.assertFalse(tx_cells_retained(self.fixture().replace('.A(RISE),.B(FALL),.X(SERIAL)',
            '.A(RISE),.B(HELD),.X(SERIAL)',1)))

    def test_missing_capture_input_is_rejected(self):
        self.assertFalse(tx_cells_retained(self.fixture().replace('.D(RNEXT),','',1)))


if __name__=='__main__':unittest.main()
