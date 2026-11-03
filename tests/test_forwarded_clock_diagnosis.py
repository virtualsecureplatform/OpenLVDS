from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diagnose_forwarded_clock as diagnosis

NETLIST = r'''
sky130_fd_sc_hd__buf_4 \clock_launch/select_clock (.A(clk_400), .X(sel));
sky130_fd_sc_hd__mux2_4 \clock_launch/output_logic (.A0(fall), .A1(rise), .S(sel), .X(mux));
sky130_fd_sc_hd__dfrtp_4 \clock_launch/rise_sample (.CLK(clk_90), .D(zero), .Q(rise));
sky130_fd_sc_hd__dfrtp_4 \clock_launch/held_sample (.CLK(clk_90), .D(one), .Q(held));
sky130_fd_sc_hd__dfrtp_4 \clock_launch/fall_sample (.CLK(clkn), .D(held), .Q(fall));
sky130_fd_sc_hd__inv_4 \clock_launch/falling_clock (.A(clk_90), .Y(clkn));
sky130_fd_sc_hd__conb_1 tie0 (.LO(zero));
sky130_fd_sc_hd__conb_1 tie1 (.HI(one));
'''


class ForwardedClockDiagnosis(unittest.TestCase):
    def test_mapped_mux_function_requires_actual_select_and_registered_constants(self):
        with patch.object(diagnosis, 'tx_buffered_paths_retained', return_value=True):
            result = diagnosis.clock_function(NETLIST)
            self.assertEqual(result['steady_function'], 'forwarded_clock = ~clk_400')
            for changed in (NETLIST.replace('.A(clk_400)', '.A(clk_90)'),
                            NETLIST.replace('.A0(fall), .A1(rise)', '.A0(rise), .A1(fall)'),
                            NETLIST.replace('.LO(zero)', '.HI(zero)'),
                            NETLIST.replace('.D(held)', '.D(one)')):
                with self.assertRaises(ValueError): diagnosis.clock_function(changed)
        with patch.object(diagnosis, 'tx_buffered_paths_retained', return_value=False):
            with self.assertRaises(ValueError): diagnosis.clock_function(NETLIST)

    def test_intended_inversion_is_not_counted_as_added_duty_distortion(self):
        t = np.arange(0, 125.001, .005) * 1e-9
        clk = lambda delay: 1.8 * (((t - delay) % 2.5e-9) < 1.125e-9)
        forwarded = lambda delay: 1.8 - clk(delay)
        txdiff = (forwarded(.3e-9) - .9) / 3
        rxdiff = (forwarded(1.5e-9) - .9) / 3
        values = [clk(0), clk(.625e-9), forwarded(.1e-9), 1.2 + txdiff / 2,
                  1.2 - txdiff / 2, 1.2 + rxdiff / 2, 1.2 - rxdiff / 2, forwarded(1.7e-9)]
        names = ['CLK0', 'CLK90', 'TXCLOCK', 'CP', 'CN', 'RCP', 'RCN', 'RXCLOCK']
        wave = np.column_stack([np.arange(len(t)), t, *values])
        header = {'V(' + n + ')': i + 2 for i, n in enumerate(names)}
        result = diagnosis.analyze(wave, header)
        self.assertAlmostEqual(result['stages']['intended_inverted_clk0']['high_width']['mean_ps'], 1375, delta=5)
        self.assertAlmostEqual(result['capture_clock_quadrature']['high_width']['mean_ps'], 1125, delta=5)
        for hop in result['propagation'].values():
            self.assertAlmostEqual(hop['mean_high_width_change_ps'], 0, delta=5)

    def test_unverified_payload_cannot_supply_a_clock_reference(self):
        with patch.object(diagnosis.original.coupled, 'verify', return_value=dict(payload_restored=False)):
            with self.assertRaises(ValueError): diagnosis.diagnose(Path('unverified'))
