# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from physical_policy import tx_cells_retained


class NativeSerializerMapping(unittest.TestCase):
    def fixture(self):
        rows=[]
        for lane,clk,select in [('data_launch','clk_400','clk_90'),
                                ('clock_launch','clk_90','clk_400')]:
            cells=[('mux2_4','output_logic','.A0(FALL),.A1(RISE),.S(SEL),.X(SERIAL)'),
                ('buf_4','select_clock',f'.A({select}),.X(SEL)'),
                ('inv_4','falling_clock_14',f'.A({clk}),.Y(CLKN)'),
                ('dfrtp_4','rise_sample',f'.CLK({clk}),.D(D0),.RESET_B(RST),.Q(RISE)'),
                ('dfrtp_4','held_sample',f'.CLK({clk}),.D(D1),.RESET_B(RST),.Q(HELD)'),
                ('dfrtp_4','fall_sample','.CLK(CLKN),.D(HELD),.RESET_B(RST),.Q(FALL)')]
            rows.extend(f'sky130_fd_sc_hd__{cell} \\{lane}/{name} ({pins});' for cell,name,pins in cells)
        return '\n'.join(rows)

    def test_matched_native_cells_and_routed_clock_name_pass(self):
        self.assertTrue(tx_cells_retained(self.fixture()))

    def test_remapped_output_gate_is_rejected(self):
        self.assertFalse(tx_cells_retained(self.fixture().replace('mux2_4','nand2_4',1)))

    def test_wrong_output_operand_is_rejected(self):
        self.assertFalse(tx_cells_retained(self.fixture().replace('.A0(FALL),.A1(RISE),.S(SEL),.X(SERIAL)',
            '.A0(HELD),.A1(RISE),.S(SEL),.X(SERIAL)',1)))

    def test_missing_capture_input_is_rejected(self):
        self.assertFalse(tx_cells_retained(self.fixture().replace('.D(D0),','',1)))

    def test_select_clock_phase_must_be_opposite_capture_domain(self):
        self.assertFalse(tx_cells_retained(self.fixture().replace('.A(clk_90),.X(SEL)',
            '.A(clk_400),.X(SEL)',1)))

    def test_second_bit_must_come_from_rising_edge_hold_register(self):
        self.assertFalse(tx_cells_retained(self.fixture().replace('.D(HELD),','.D(D1),',1)))


if __name__=='__main__':unittest.main()
