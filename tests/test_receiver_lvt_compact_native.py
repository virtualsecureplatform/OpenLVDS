# SPDX-License-Identifier: GPL-3.0-only
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_receiver_lvt_compact as native


class CompactLvtNative(unittest.TestCase):
    DECK='Title\n.tran 5p 80n 0 5p\n.print tran V(RCP) V(RCN) V(RXCLOCK)\n.end\n'

    def test_missing_geometry_cannot_prepare_or_start_a_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'build/diagnostics/clock_restore/parent';layout=root/'build/diagnostics/receiver_layout/missing'
            with patch.object(native,'ROOT',root),patch.object(native,'engine',return_value='ngspice'),patch.object(native.subprocess,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete the audited'):native.prepare(parent,layout,root/'dc',root/'clock')
                run.assert_not_called()

    def test_exact_profile_cannot_accept_a_different_source_or_placement(self):
        native.validate_profile(native.PROFILE)
        for fields in [dict(clamp_variant='unclamped_tail_headroom'),dict(diagnostic_stage='all_passed'),
                dict(placement='original one-row placement')]:
            with self.assertRaisesRegex(ValueError,'exact compact LVT'):native.validate_profile(dict(native.PROFILE,**fields))

    def test_missing_full_dc_refuses_before_source_clock_or_native_execution(self):
        with patch.object(native.source_clock,'static_gate',side_effect=ValueError('Complete all fifteen')) as gate,patch.object(native.source_clock,'run') as run:
            with self.assertRaisesRegex(ValueError,'Complete all fifteen'):native.source_gate(Path('dc'),Path('clock'))
            gate.assert_called_once();run.assert_not_called()

    def test_missing_source_results_cannot_launch_a_source_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);screen=root/'dc';clock=root/'build/diagnostics/receiver_clamp/clock';clock.mkdir(parents=True)
            manifest=dict(identity=dict(static_screen='dc',static_proofs={}),tasks=[dict(id='missing')])
            (clock/'manifest.json').write_text(json.dumps(manifest))
            with patch.object(native,'ROOT',root),patch.object(native.source_clock,'static_gate',return_value={}),patch.object(native.source_clock,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete all three'):native.source_gate(screen,clock)
                run.assert_not_called()

    def test_only_original_maximum_step_changes_with_all_other_clock_parameters_fixed(self):
        result=native.replay_deck(self.DECK,1)
        self.assertEqual(result,self.DECK.replace('0 5p','0 1p'));self.assertEqual(native.replay_deck(result,1),result)
        for step in [5,2,True]:
            with self.assertRaisesRegex(ValueError,'1 ps'):native.replay_deck(self.DECK,step)
        for deck in [self.DECK.replace('80n','79n'),self.DECK.replace('.tran 5p','.tran 10p')]:
            with self.assertRaises(ValueError):native.replay_deck(deck,1)

    def fixture(self,root):
        out=root/'build/diagnostics/receiver_replay/scaled';out.mkdir(parents=True)
        (out/'library.spice').write_text('* pinned model\n');tasks=[]
        for name in ['captured','sharp_control']:
            folder=out/name;folder.mkdir();(folder/'bench.cir').write_text(native.replay_deck(self.DECK,1))
            tasks.append(dict(id=name,deck_sha256=native.digest(folder/'bench.cir')))
        identity=dict(copy.deepcopy(native.PROFILE),native_maximum_step_ps=1,source_maximum_step_ps=1,
            replay_parallel_jobs=2,simulator_provenance='runtime',code={},inputs={},observation_nodes={})
        manifest=dict(identity=identity,tasks=tasks,library_sha256=native.digest(out/'library.spice'))
        (out/'manifest.json').write_text(json.dumps(manifest));return out,manifest

    def test_partial_traces_are_preserved_without_launching_or_overwriting_either_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out,manifest=self.fixture(root)
            for t in manifest['tasks']:(out/t['id']/'bench.raw').write_bytes(b'partial original trace')
            with patch.object(native,'ROOT',root),patch.object(native,'provenance',return_value='runtime'),patch.object(native,'lease') as lease,patch.object(native.subprocess,'run') as run:
                with self.assertRaisesRegex(ValueError,'Incomplete native execution retained'):native.run(out,[1,3])
                run.assert_not_called();lease.assert_not_called()
            for t in manifest['tasks']:self.assertEqual((out/t['id']/'bench.raw').read_bytes(),b'partial original trace')
            self.assertEqual(json.loads((out/'execution.json').read_text())['status'],'held_for_diagnosis')

    def test_cached_controls_remeasure_actual_waveforms_without_simulations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out,manifest=self.fixture(root)
            transport=dict(missing_output_edges=0,pulses=[dict(output_edges_in_next_input_period=1) for _ in range(47)])
            for task in manifest['tasks']:
                folder=out/task['id'];(folder/'bench.cir.prn').write_text('immutable waveform fixture')
                report=dict(copy.deepcopy(native.PROFILE),task=task['id'],qualified_phy=False,qualification_verdict=None,
                    native_maximum_step_ps=1,receiver_transport=transport,
                    clock_internal_node_ranges_v={},manifest_sha256=native.digest(out/'manifest.json'),
                    deck_sha256=task['deck_sha256'],waveform_sha256=native.digest(folder/'bench.cir.prn'))
                (folder/'summary.json').write_text(json.dumps(report))
            wave=np.zeros((3,5));wave[:,1]=[0,40e-9,80e-9]
            headers={'V(RCP)':2,'V(RCN)':3,'V(RXCLOCK)':4}
            with patch.object(native,'ROOT',root),patch.object(native,'provenance',return_value='runtime'),patch.object(native,'read_wave',return_value=(wave,headers)) as read,patch.object(native,'pulse_transport',return_value=transport),patch.object(native,'lease') as lease,patch.object(native.subprocess,'run') as run:
                native.run(out,[1,3]);self.assertEqual(read.call_count,2);lease.assert_not_called();run.assert_not_called()
                report=json.loads((out/'summary.json').read_text());self.assertTrue(report['native_clock_passed']);self.assertFalse(report['qualified_phy'])
                wave[-1,1]=70e-9
                with self.assertRaisesRegex(ValueError,'Incomplete original 80 ns'):native.run(out,[1,3])
                lease.assert_not_called();run.assert_not_called()


if __name__=='__main__':unittest.main()
