# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_light_decision_candidate as physical
import probe_receiver_light_decision_candidate as replay
from receiver_light_decision_experiment import source_variant,previous_source
from layout import circuits,flatten
SOURCE=(Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text()


class LightDecisionPhysicalGate(unittest.TestCase):
    def fixture(self,root,factory=source_variant):
        (root/'analog').mkdir();(root/'analog/openlvds.spice').write_text(SOURCE)
        screen=root/'build/diagnostics/receiver_clamp/test';screen.mkdir(parents=True);tasks=[];results=[]
        for name in sorted(physical.CASES):
            folder=screen/name;folder.mkdir();tasks.append(dict(id=name))
            (folder/'candidate.spice').write_text(factory(SOURCE,name.startswith('clamped_')))
            for leaf in ['library.spice','bench.cir','bench.cir.prn','summary.json']:(folder/leaf).write_text('{}')
            results.append(dict(task=name,receiver_transport=dict(missing_output_edges=0,pulses=[dict(output_edges_in_next_input_period=1)])))
        (screen/'manifest.json').write_text(json.dumps(dict(tasks=tasks)))
        (screen/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,results=results)))
        return screen

    def test_source_gate_binds_exact_original_decision_source(self):
        for factory,valid in [(source_variant,True),(previous_source,False)]:
            with self.subTest(valid=valid),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);screen=self.fixture(root,factory)
                with patch.object(physical,'ROOT',root),patch.object(physical,'recheck'):
                    if valid:self.assertEqual(len(physical.source_gate(screen)),17)
                    else:
                        with self.assertRaisesRegex(ValueError,'another receiver source'):physical.source_gate(screen)

    def test_repeated_edges_hold_physical_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);screen=self.fixture(root);path=screen/'summary.json';summary=json.loads(path.read_text())
            summary['results'][0]['receiver_transport']['pulses'][0]['output_edges_in_next_input_period']=2
            path.write_text(json.dumps(summary))
            with patch.object(physical,'ROOT',root),patch.object(physical,'recheck'):
                with self.assertRaisesRegex(ValueError,'loses or repeats'):physical.source_gate(screen)

    def test_clamp_placement_preserves_all_smaller_decision_devices(self):
        _,devices=flatten(circuits(source_variant(SOURCE,True)),'openlvds_receiver_core');ordered=physical.place_clamp(devices)
        self.assertEqual({d['name']:d for d in ordered},{d['name']:d for d in devices})
        clamp=lambda d:'__XTRACK__' in d['name'] or d['name'].endswith(('__XCLAMP0','__XCLAMP1','__XCLAMP2','__XCLAMP3'))
        self.assertEqual([d for d in ordered if not clamp(d)],[d for d in devices if not clamp(d)])

    def test_native_preparation_rejects_doubled_decision_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);layout=root/'build/diagnostics/receiver_layout/test';layout.mkdir(parents=True)
            identity=dict(input_tail_scale=2,decision_clamped=True,clamp_variant='strong_light_decision',decision_scale=2)
            (layout/'summary.json').write_text(json.dumps(dict(identity=identity)));(layout/'extraction.json').write_text('{}')
            with patch.object(replay,'ROOT',root),patch.object(replay,'engine',return_value='ngspice'),patch.object(replay,'source_gate') as gate:
                with self.assertRaisesRegex(ValueError,'original-decision'):replay.prepare(root/'build/diagnostics/clock_restore/test',layout)
            gate.assert_not_called()
