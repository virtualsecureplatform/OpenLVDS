# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_tail_headroom_candidate as physical
import probe_receiver_tail_headroom_candidate as replay
from receiver_tail_headroom_experiment import source_variant,previous_source
SOURCE=(Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text()


class TailHeadroomPhysicalGate(unittest.TestCase):
    def static_fixture(self,root,factory=source_variant,count=15,passed=True):
        (root/'analog').mkdir();(root/'analog/openlvds.spice').write_text(SOURCE)
        screen=root/'build/diagnostics/receiver_tail_headroom_matrix/test';screen.mkdir(parents=True)
        children=[]
        for index in range(count):
            folder=root/f'build/diagnostics/receiver_tail_headroom_static/{index}';folder.mkdir(parents=True)
            children.append(dict(root=str(folder.relative_to(root))))
            (folder/'source.spice').write_text(factory(SOURCE))
            (folder/'summary.json').write_text(json.dumps(dict(reduced_decision_tail=dict(
                metrics=dict(passed=passed,points=[dict(passed=passed)]*12)))))
            for name in ['manifest.json','bench.cir','bench.cir.prn']:(folder/name).write_text('{}')
        (screen/'manifest.json').write_text(json.dumps(dict(identity=dict(children=children))))
        (screen/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,dc_all_passed=passed,required=count)))
        return screen,children

    def test_static_gate_remeasures_all_fifteen_exact_sources(self):
        for factory,passed,valid in [(source_variant,True,True),(previous_source,True,False),
                                     (source_variant,False,False)]:
            with self.subTest(valid=valid),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);screen,_=self.static_fixture(root,factory,passed=passed)
                with patch.object(physical,'ROOT',root),patch.object(physical.dc,'run') as remeasure:
                    if valid:self.assertEqual(len(physical.static_gate(screen)),77)
                    else:
                        with self.assertRaises(ValueError):physical.static_gate(screen)
                    remeasure.assert_called_once_with(screen)

    def test_missing_child_or_summary_never_starts_a_scientific_child(self):
        for missing in ['child','matrix','coverage']:
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);screen,children=self.static_fixture(root,count=14 if missing=='coverage' else 15)
                if missing=='child':(root/children[0]['root']/'summary.json').unlink()
                if missing=='matrix':(screen/'summary.json').unlink()
                with patch.object(physical,'ROOT',root),patch.object(physical.dc,'run') as remeasure:
                    with self.assertRaises(ValueError):physical.static_gate(screen)
                    remeasure.assert_not_called()

    def test_one_failed_original_sample_holds_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);screen,children=self.static_fixture(root)
            path=root/children[0]['root']/'summary.json';report=json.loads(path.read_text())
            report['reduced_decision_tail']['metrics']['points'][10]['passed']=False
            path.write_text(json.dumps(report))
            with patch.object(physical,'ROOT',root),patch.object(physical.dc,'run'):
                with self.assertRaisesRegex(ValueError,'every original sample'):physical.static_gate(screen)

    def source_fixture(self,root,factory=source_variant):
        (root/'analog').mkdir();(root/'analog/openlvds.spice').write_text(SOURCE)
        screen=root/'build/diagnostics/receiver_clamp/test';screen.mkdir(parents=True);tasks=[];results=[]
        for name in sorted(physical.CASES):
            folder=screen/name;folder.mkdir();tasks.append(dict(id=name))
            (folder/'candidate.spice').write_text(factory(SOURCE,name.startswith('clamped_')))
            for leaf in ['library.spice','bench.cir','bench.cir.prn','summary.json']:(folder/leaf).write_text('{}')
            results.append(dict(task=name,receiver_transport=dict(missing_output_edges=0,
                pulses=[dict(output_edges_in_next_input_period=1)])))
        (screen/'manifest.json').write_text(json.dumps(dict(tasks=tasks)))
        (screen/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,results=results)))
        return screen

    def test_source_gate_rejects_original_tail_or_repeated_clock_edges(self):
        for factory,repeat,valid in [(source_variant,False,True),(previous_source,False,False),
                                      (source_variant,True,False)]:
            with self.subTest(valid=valid,repeat=repeat),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);screen=self.source_fixture(root,factory)
                if repeat:
                    path=screen/'summary.json';report=json.loads(path.read_text())
                    report['results'][0]['receiver_transport']['pulses'][0]['output_edges_in_next_input_period']=2
                    path.write_text(json.dumps(report))
                with patch.object(physical,'ROOT',root),patch.object(physical,'recheck'),patch.object(physical,'static_gate',return_value={}):
                    if valid:self.assertEqual(len(physical.source_gate(screen,root/'dc')),17)
                    else:
                        with self.assertRaises(ValueError):physical.source_gate(screen,root/'dc')

    def test_native_gate_rejects_wrong_tail_width_or_model_before_rechecking(self):
        for field,value in [('decision_tail_width_um',64),('decision_tail_scale',1),
                             ('first_restoration_nfet_model','sky130_fd_pr__nfet_01v8_lvt')]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);layout=root/'build/diagnostics/receiver_layout/test';layout.mkdir(parents=True)
                identity=dict(input_tail_scale=2,decision_scale=1,decision_tail_scale=0.25,decision_tail_width_um=16,
                    decision_clamped=False,clamp_variant='unclamped_tail_headroom',parallel_clamp_units=0,
                    clamp_reference=None,replica_monitor_unloaded=True,restoration_widths_um=[[8,4],[16,8],[16,8]],
                    first_restoration_nfet_model='sky130_fd_pr__nfet_01v8')
                identity[field]=value
                (layout/'summary.json').write_text(json.dumps(dict(identity=identity)));(layout/'extraction.json').write_text('{}')
                with patch.object(replay,'ROOT',root),patch.object(replay,'engine',return_value='ngspice'),patch.object(replay,'source_gate') as gate:
                    with self.assertRaises(ValueError):replay.prepare(root/'build/diagnostics/clock_restore/test',layout)
                    gate.assert_not_called()


if __name__=='__main__':unittest.main()
