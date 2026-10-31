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


class StrongPublicationPolicy(unittest.TestCase):
    def source(self):return (Path(__file__).resolve().parents[1]/'rtl/experiments/openlvds_ddr_rx_buffer8_publish4.v').read_text()

    def test_stronger_source_has_a_distinct_explicit_topology_policy(self):
        from rx_buffered_policy import policy_parameters
        source=self.source();params=policy_parameters('public-data-buf8-publish4')
        self.assertTrue(retained(source,**params));self.assertFalse(retained(source))
        self.assertFalse(retained(source.replace('__dfrtp_4','__dfrtp_1',1),**params))
        self.assertFalse(retained(source.replace('.CLK(clk),.D(publish_input[0])','.CLK(clk_n),.D(publish_input[0])'),**params))
        self.assertFalse(retained(source.replace('.Q(published_data[0])','.Q(other)'),**params))
        with self.assertRaises(ValueError):policy_parameters('unknown')


class PublicationCellComparison(unittest.TestCase):
    def test_unit_publication_is_separately_declared_and_cannot_inherit_strength4(self):
        from rx_buffered_policy import policy_parameters
        source=(Path(__file__).resolve().parents[1]/'rtl/experiments/openlvds_ddr_rx_buffer8_publish1.v').read_text()
        self.assertTrue(retained(source,**policy_parameters('public-data-buf8-publish1')))
        self.assertFalse(retained(source,**policy_parameters('public-data-buf8-publish4')))
        self.assertFalse(retained(source.replace('__dfrtp_1 data0_publish','__dfrtp_4 data0_publish'),**policy_parameters('public-data-buf8-publish1')))


class EarlyPublicationPolicy(unittest.TestCase):
    def test_half_cycle_topology_and_enable_membership_are_enforced(self):
        from rx_buffered_policy import policy_parameters
        source=(Path(__file__).resolve().parents[1]/'rtl/experiments/openlvds_ddr_rx_early.v').read_text()
        params=policy_parameters('half-cycle-publish-buf4')
        self.assertTrue(retained(source,**params));self.assertFalse(retained(source))
        changes=[source.replace('__inv_4','__inv_1'),
            source.replace('held_rise(.CLK(clk_n)','held_rise(.CLK(clk)'),
            source.replace('valid_sample(.CLK(clk_n)','valid_sample(.CLK(clk)'),
            source.replace('pair_start(.CLK(clk)','pair_start(.CLK(clk_n)'),
            source.replace('fall_enable(.A(fall_bit)','fall_enable(.A(rise_bit)'),
            source.replace('rise_enable(.A(rise_bit),.B(run)','rise_enable(.A(rise_bit),.B(serial)'),
            source.replace('valid_enable(.A(pair_started)','valid_enable(.A(rise_bit)'),
            source.replace('valid_drive(.A(held_valid)','valid_drive(.A(pair_started)'),
            source.replace('data0_drive(.A(held_bit)','data0_drive(.A(rise_bit)')]
        for changed in changes:self.assertFalse(retained(changed,**params))
        self.assertFalse(retained(source,early_publish=True,strength=8))
