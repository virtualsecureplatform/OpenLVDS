# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import benchmark_compensated_driver_exact as flow
from dll_campaign import text_block
from exact_rc_candidate import parse, static_signature
from spice_scope import closure_hash

MODEL = '''.subckt openlvds_driver_core D P N VSS
X1 P D VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=1 ad=2 as=2 pd=3 ps=3
C1 sense VSS 1p
R1 P center 1
R2 N center 2
R3 sense center 3
R4 D saved 1
R5 saved sense 2
.ends openlvds_driver_core
.subckt lvds_bias IREF NB VSS
X2 IREF IREF VSS VSS sky130_fd_pr__nfet_01v8 w=1 l=1
.ends lvds_bias
.subckt openlvds_driver D P N VSS
XCORE D P N VSS openlvds_driver_core
XB D N VSS lvds_bias
.ends openlvds_driver
'''
DECK = '''XD D P N 0 openlvds_driver
.print tran V(P) V(N) V(XD:XCORE:saved)
.save V(XD:XCORE:sense)
.end
'''


class CompensatedDriverExact(unittest.TestCase):
    def test_exact_candidate_retains_saved_resistor_only_node_and_physical_statements(self):
        result, proof = flow.candidate(MODEL, DECK)
        before = parse(text_block(MODEL, flow.TOP))
        after = parse(text_block(result, flow.TOP))
        self.assertEqual(static_signature(before), static_signature(after))
        self.assertIn('saved', after['graph'])
        self.assertNotIn('center', after['graph'])
        self.assertTrue(proof['witness']['passed'])
        self.assertEqual(proof['algebraic_nodes_eliminated'], 1)
        self.assertEqual(closure_hash(MODEL, 'lvds_bias'), closure_hash(result, 'lvds_bias'))

    def test_failed_mathematical_witness_cannot_produce_candidate(self):
        with patch.object(flow.exact, 'witness', return_value={'passed': False}):
            with self.assertRaisesRegex(ValueError, 'witnesses failed'):
                flow.candidate(MODEL, DECK)

    def test_missing_saved_probe_is_rejected(self):
        with self.assertRaises(ValueError):
            flow.candidate(MODEL, DECK.replace(':saved)', ':missing)'))

    def wave(self, delay=0, internal_error=0):
        t = np.linspace(0, 80e-9, 80001)
        d = .3 * np.sin(2 * np.pi * 400e6 * (t - delay))
        return ['time', 'v(p)', 'v(n)', 'v(internal)'], np.column_stack(
            [t, 1.2 + d / 2, 1.2 - d / 2, np.zeros(len(t)) + internal_error])

    def test_comparison_checks_internal_voltages_and_both_edge_polarities(self):
        baseline = self.wave()
        self.assertTrue(flow.agreement(baseline, self.wave())['passed'])
        self.assertFalse(flow.agreement(baseline, self.wave(internal_error=.021))['passed'])
        self.assertFalse(flow.agreement(baseline, self.wave(delay=25e-12))['passed'])
        with self.assertRaisesRegex(ValueError, 'observations changed'):
            flow.agreement(baseline, (['time', 'v(p)', 'v(n)', 'v(other)'], baseline[1]))

    def test_zero_edge_trace_cannot_pass(self):
        names, wave = self.wave()
        wave[:, 1:3] = 1.2
        self.assertFalse(flow.agreement((names, wave), (names, wave))['passed'])

    def test_partial_execution_is_retained_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'bench.raw').write_bytes(b'partial')
            with patch.object(flow, 'bound'), patch.object(flow, 'command') as command:
                with self.assertRaisesRegex(ValueError, 'no retry'):
                    flow.run(folder)
                command.assert_not_called()

    def test_return_code_alone_cannot_admit_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'execution.json').write_text('{"returncode":0,"status":"process_completed"}')
            with patch.object(flow, 'bound', return_value={}), patch.object(flow, 'sha', return_value='x'):
                with self.assertRaisesRegex(ValueError, 'bound complete'):
                    flow.compare(folder)


if __name__ == '__main__':
    unittest.main()
