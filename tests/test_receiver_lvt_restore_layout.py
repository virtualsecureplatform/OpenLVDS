# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_lvt_restore_candidate as physical
import probe_receiver_lvt_restore_candidate as replay
from receiver_lvt_restore_experiment import source_variant,previous_source
from layout import circuits,flatten
SOURCE=(Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text()


class LvtRestorePhysicalGate(unittest.TestCase):
    def test_static_gate_binds_actual_lvt_source_and_every_original_dc_sample(self):
        for factory,passed,valid in [(source_variant,True,True),(previous_source,True,False),
                                     (source_variant,False,False)]:
            with self.subTest(factory=factory.__module__,passed=passed),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                (root/'analog').mkdir();(root/'analog/openlvds.spice').write_text(SOURCE)
                screen=root/'build/diagnostics/receiver_lvt_static/test';screen.mkdir(parents=True)
                (screen/'manifest.json').write_text(json.dumps(dict(identity=dict(case='schematic_receiver_tt_25'))))
                (screen/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,lvt_first_stage=dict(
                    metrics=dict(passed=passed,points=[dict(passed=passed)]*12)))))
                (screen/'source.spice').write_text(factory(SOURCE))
                for name in ['bench.cir','bench.cir.prn']:(screen/name).write_text('test')
                with patch.object(physical,'ROOT',root),patch.object(physical.dc,'run') as remeasure:
                    if valid:self.assertEqual(len(physical.static_gate(screen)),5)
                    else:
                        with self.assertRaises(ValueError):physical.static_gate(screen)
                    remeasure.assert_called_once_with(screen)

    def test_incomplete_static_gate_never_launches_a_scientific_child(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);screen=root/'build/diagnostics/receiver_lvt_static/test';screen.mkdir(parents=True)
            with patch.object(physical,'ROOT',root),patch.object(physical.dc,'run') as execute:
                with self.assertRaisesRegex(ValueError,'Complete the LVT static'):physical.static_gate(screen)
                execute.assert_not_called()

    def test_native_gate_rejects_standard_first_nfet_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);layout=root/'build/diagnostics/receiver_layout/test';layout.mkdir(parents=True)
            identity=dict(input_tail_scale=2,decision_clamped=False,clamp_variant='unclamped_lvt_restore',decision_scale=1,
                parallel_clamp_units=0,clamp_reference=None,replica_monitor_unloaded=True,
                restoration_widths_um=[[8,4],[16,8],[16,8]],first_restoration_nfet_model='sky130_fd_pr__nfet_01v8')
            (layout/'summary.json').write_text(json.dumps(dict(identity=identity)));(layout/'extraction.json').write_text('{}')
            with patch.object(replay,'ROOT',root),patch.object(replay,'engine',return_value='ngspice'),patch.object(replay,'source_gate') as gate:
                with self.assertRaisesRegex(ValueError,'LVT first-stage restoration'):replay.prepare(root/'build/diagnostics/clock_restore/test',layout)
            gate.assert_not_called()

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

    def test_source_gate_binds_exact_stronger_restoration_source(self):
        for factory,valid in [(source_variant,True),(previous_source,False)]:
            with self.subTest(valid=valid),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);screen=self.fixture(root,factory)
                with patch.object(physical,'ROOT',root),patch.object(physical,'recheck'),patch.object(physical,'static_gate',return_value={}):
                    if valid:self.assertEqual(len(physical.source_gate(screen,root/'static')),17)
                    else:
                        with self.assertRaisesRegex(ValueError,'another receiver source'):physical.source_gate(screen,root/'static')

    def test_repeated_edges_hold_physical_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);screen=self.fixture(root);path=screen/'summary.json';summary=json.loads(path.read_text())
            summary['results'][0]['receiver_transport']['pulses'][0]['output_edges_in_next_input_period']=2
            path.write_text(json.dumps(summary))
            with patch.object(physical,'ROOT',root),patch.object(physical,'recheck'),patch.object(physical,'static_gate',return_value={}):
                with self.assertRaisesRegex(ValueError,'loses or repeats'):physical.source_gate(screen,root/'static')

    def test_clamp_placement_preserves_all_devices(self):
        _,devices=flatten(circuits(source_variant(SOURCE,True)),'openlvds_receiver_core');ordered=physical.place_monitor(devices)
        self.assertEqual({d['name']:d for d in ordered},{d['name']:d for d in devices})
        clamp=lambda d:'__XTRACK__' in d['name'] or d['name'].endswith(('__XCLAMP0','__XCLAMP1','__XCLAMP2','__XCLAMP3'))
        self.assertEqual([d for d in ordered if not clamp(d)],[d for d in devices if not clamp(d)])

    def test_native_preparation_rejects_doubled_decision_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);layout=root/'build/diagnostics/receiver_layout/test';layout.mkdir(parents=True)
            identity=dict(first_restoration_nfet_model='sky130_fd_pr__nfet_01v8_lvt',input_tail_scale=2,decision_clamped=True,clamp_variant='strong_fast_restore',decision_scale=2,parallel_clamp_units=0,clamp_reference=None,replica_monitor_unloaded=True,restoration_widths_um=[[8,4],[16,8],[16,8]])
            (layout/'summary.json').write_text(json.dumps(dict(identity=identity)));(layout/'extraction.json').write_text('{}')
            with patch.object(replay,'ROOT',root),patch.object(replay,'engine',return_value='ngspice'),patch.object(replay,'source_gate') as gate:
                with self.assertRaisesRegex(ValueError,'LVT first-stage restoration'):replay.prepare(root/'build/diagnostics/clock_restore/test',layout)
            gate.assert_not_called()

    def test_native_preparation_rejects_any_clamp_reference_or_loaded_monitor(self):
        for reference,unloaded in [('VREF',True),(None,False)]:
            with self.subTest(reference=reference,unloaded=unloaded),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);layout=root/'build/diagnostics/receiver_layout/test';layout.mkdir(parents=True)
                identity=dict(first_restoration_nfet_model='sky130_fd_pr__nfet_01v8_lvt',input_tail_scale=2,decision_clamped=False,clamp_variant='unclamped_lvt_restore',decision_scale=1,
                              parallel_clamp_units=0,clamp_reference=reference,replica_monitor_unloaded=unloaded,restoration_widths_um=[[8,4],[16,8],[16,8]])
                (layout/'summary.json').write_text(json.dumps(dict(identity=identity)));(layout/'extraction.json').write_text('{}')
                with patch.object(replay,'ROOT',root),patch.object(replay,'engine',return_value='ngspice'),patch.object(replay,'source_gate') as gate:
                    with self.assertRaisesRegex(ValueError,'LVT first-stage restoration'):replay.prepare(root/'build/diagnostics/clock_restore/test',layout)
                gate.assert_not_called()

    def test_native_preparation_rejects_previous_restoration_widths(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);layout=root/'build/diagnostics/receiver_layout/test';layout.mkdir(parents=True)
            identity=dict(first_restoration_nfet_model='sky130_fd_pr__nfet_01v8_lvt',input_tail_scale=2,decision_clamped=False,clamp_variant='unclamped_lvt_restore',decision_scale=1,
                          parallel_clamp_units=0,clamp_reference=None,replica_monitor_unloaded=True,
                          restoration_widths_um=[[4,2],[8,4],[16,8]])
            (layout/'summary.json').write_text(json.dumps(dict(identity=identity)));(layout/'extraction.json').write_text('{}')
            with patch.object(replay,'ROOT',root),patch.object(replay,'engine',return_value='ngspice'),patch.object(replay,'source_gate') as gate:
                with self.assertRaisesRegex(ValueError,'LVT first-stage restoration'):replay.prepare(root/'build/diagnostics/clock_restore/test',layout)
            gate.assert_not_called()
