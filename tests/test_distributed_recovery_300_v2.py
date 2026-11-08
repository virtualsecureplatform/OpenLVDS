# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diagnose_distributed_recovery_300_v2 as p
import test_bank_stage_history_300 as fixtures


class RecoveryTests(unittest.TestCase):
    def test_stage_assignment_comes_from_actual_topology_for_every_variant(self):
        parent = p.ROOT / 'build/diagnostics/distributed_fine_pilot_300_v1/f07675577cda70f9'
        identity = json.loads((parent / 'manifest.json').read_text())['identity']
        expected = {'strong_pre_c4': (0, 24), 'strong_pre_c2': (0, 12),
                    'split_c1_c1': (6, 6), 'split_c2_c2': (12, 12)}
        for variant, counts in expected.items():
            obs = identity['observations'][variant]
            nodes = p.switch_nodes(obs, (parent / variant / 'bank.spice').read_text(),
                                   identity['revisions'][variant]['macro_top'])
            self.assertEqual(tuple(sum(v['stage'] == stage for v in nodes.values())
                                   for stage in ('pre', 'fine')), counts)
            mapped = {d['name']: d for d in obs['devices']}
            for node, info in nodes.items():
                self.assertIn(node, mapped[info['device']]['terminals'])
                self.assertEqual(info['signal_node'],
                                 'XD:pre_out' if info['stage'] == 'pre' else 'XD:fine_node')

    def test_all_eight_pretransition_samples_and_missing_event_rejection(self):
        t, v, _, _ = fixtures.StageHistoryTests().fixture()
        proof = p.samples(t, v['XD:pre_out'], {'fine': v['XD:fine_node']})
        self.assertEqual(len(proof['nodes']['fine']['before_input_rising_voltage_v']), 8)
        changed = v['XD:pre_out'].copy(); changed[t > 24000] = 0
        with self.assertRaises(ValueError):
            p.samples(t, changed, {'fine': v['XD:fine_node']})

    def test_truncation_and_nonfinite_native_observations_rejected(self):
        t, v, _, _ = fixtures.StageHistoryTests().fixture()
        with self.assertRaises(ValueError):
            p.samples(t[:-100], v['XD:pre_out'][:-100], {'fine': v['XD:fine_node'][:-100]})
        changed = v['XD:fine_node'].copy(); changed[10] = np.nan
        with self.assertRaises(ValueError):
            p.samples(t, v['XD:pre_out'], {'fine': changed})
