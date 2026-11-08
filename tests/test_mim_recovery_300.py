# SPDX-License-Identifier: GPL-3.0-only
import json,sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bank_stage_history_300_v2 as p
import replay_bank_300_v2 as replay
import test_bank_stage_history_300 as fixtures
import test_replay_bank_300 as timing_fixtures

class MimRecoveryTests(unittest.TestCase):
    def test_stage_and_outer_timing_algorithms_keep_original_results(self):
        t,v,s,r=fixtures.StageHistoryTests().fixture();result=p.stages(t,v,s,r)
        self.assertLess(result['rise']['maximum_stage_sum_residual_ps'],1e-6)
        t,a,b,s=timing_fixtures.BankReplay300Tests().trace();r=replay.independent_timing(t,a,b,s)
        self.assertAlmostEqual(r['zero_code_fast_quarter_headroom_ps'],56.45161290322585)
    def test_samples_actual_pretransition_voltages_and_rejects_missing_events(self):
        t,v,s,r=fixtures.StageHistoryTests().fixture()
        result=p.recovery_samples(t,v['XD:pre_out'],{'fine':v['XD:fine_node']})
        self.assertEqual(len(result['nodes']['fine']['before_pre_out_rise_voltage_v']),8)
        self.assertTrue(result['capacitor_charge_not_measured'])
        changed=v['XD:pre_out'].copy();changed[t>24000]=0
        with self.assertRaises(ValueError):p.recovery_samples(t,changed,{'fine':v['XD:fine_node']})
    def test_cap_side_nodes_are_actual_saved_native_mos_terminals(self):
        root=Path(__file__).resolve().parents[1]
        i=json.loads((root/'build/diagnostics/native_bank_mim4_300_v1/a8105c49e52731af/manifest.json').read_text())['identity']['source_identity']
        nodes=p.cap_side_nodes(i['observations']);self.assertEqual(len(nodes),6)
        mapped={d['name']:d for d in i['observations']['devices']}
        for node,info in nodes.items():self.assertIn(node,mapped[info['device']]['terminals'])
