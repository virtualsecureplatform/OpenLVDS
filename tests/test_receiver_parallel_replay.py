# SPDX-License-Identifier: GPL-3.0-only
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_receiver_light_clamp_candidate as replay


class ParallelReceiverReplay(unittest.TestCase):
    def exercise(self,root,fail_captured=False):
        artifact=root/'build/diagnostics/receiver_replay/test';artifact.mkdir(parents=True)
        (artifact/'library.spice').write_text('* test model\n');tasks=[]
        for name in ['captured','sharp_control']:
            folder=artifact/name;folder.mkdir();(folder/'bench.cir').write_text('* '+name+'\n')
            tasks.append(dict(id=name,deck_sha256=replay.digest(folder/'bench.cir')))
        identity=dict(replay_parallel_jobs=2,simulator_provenance={},code={},inputs={},observation_nodes={},
                      input_tail_scale=2,decision_scale=1,restoration='test')
        manifest=dict(identity=identity,tasks=tasks,library_sha256=replay.digest(artifact/'library.spice'))
        (artifact/'manifest.json').write_text(json.dumps(manifest))
        barrier=threading.Barrier(2);sharp_done=threading.Event();started=[]
        def simulate(args,**kwargs):
            folder=Path(args[0]).parent;started.append(folder.name)
            barrier.wait(timeout=5)
            if folder.name=='captured':
                if not sharp_done.wait(timeout=5):raise AssertionError('Other fixture did not run concurrently')
            else:sharp_done.set()
            if fail_captured and folder.name=='captured':return subprocess.CompletedProcess(args,7,'','failed test simulation')
            (folder/'bench.cir.prn').write_text('test waveform '+folder.name)
            return subprocess.CompletedProcess(args,0,'','')
        wave=np.array([[0,0,1,0,1.8],[1,15e-9,1,0,1.8],[2,75e-9,1,0,1.8],[3,80e-9,1,0,1.8]])
        header={'V(RCP)':2,'V(RCN)':3,'V(RXCLOCK)':4}
        transport=dict(missing_output_edges=0,pulses=[dict(output_edges_in_next_input_period=1)])
        with patch.object(replay,'ROOT',root),patch.object(replay,'provenance',return_value={}),\
             patch.object(replay,'command',side_effect=lambda log,deck:[str(deck)]),\
             patch.object(replay,'slot',side_effect=lambda:nullcontext()) as slots,\
             patch.object(replay.subprocess,'run',side_effect=simulate),\
             patch.object(replay,'read_wave',return_value=(wave,header)),\
             patch.object(replay,'pulse_transport',return_value=transport):
            if fail_captured:
                with self.assertRaises(subprocess.CalledProcessError):replay.run(artifact)
            else:replay.run(artifact)
            self.assertEqual(slots.call_count,2)
        self.assertCountEqual(started,['captured','sharp_control'])
        return artifact

    def test_both_independent_fixtures_start_and_keep_manifest_report_order(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact=self.exercise(Path(temp));summary=json.loads((artifact/'summary.json').read_text())
            self.assertEqual([r['task'] for r in summary['results']],['captured','sharp_control'])
            self.assertTrue(summary['diagnostic_complete']);self.assertFalse(summary['qualified_phy'])
            for name in ['captured','sharp_control']:
                self.assertEqual(json.loads((artifact/name/'execution.json').read_text())['status'],'completed')

    def test_one_simulator_failure_does_not_interrupt_the_other_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact=self.exercise(Path(temp),fail_captured=True)
            self.assertTrue((artifact/'sharp_control/summary.json').exists())
            self.assertFalse((artifact/'captured/summary.json').exists())
            self.assertFalse((artifact/'summary.json').exists())

    def test_vref_variant_also_runs_both_controls_and_preserves_the_other_on_failure(self):
        import probe_receiver_vref_clamp_candidate as selected
        for fail in [False,True]:
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as temp,patch.dict(globals(),replay=selected):
                artifact=self.exercise(Path(temp),fail_captured=fail)
                self.assertTrue((artifact/'sharp_control/summary.json').exists())
                self.assertEqual((artifact/'summary.json').exists(),not fail)
