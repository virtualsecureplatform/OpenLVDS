# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_wide_input_candidate as physical
import probe_receiver_wide_input_candidate as replay
from layout import circuits,flatten
from receiver_wide_input_experiment import source_variant,previous_source

SOURCE=(Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text()


class WideInputPhysicalGate(unittest.TestCase):
    def fixture(self,root,wide=True):
        (root/'analog').mkdir();(root/'analog/openlvds.spice').write_text(SOURCE)
        screen=root/'build/diagnostics/receiver_clamp/test';screen.mkdir(parents=True)
        tasks=[];results=[]
        for name in sorted(physical.CASES):
            folder=screen/name;folder.mkdir();tasks.append(dict(id=name))
            factory=source_variant if wide else previous_source
            (folder/'candidate.spice').write_text(factory(SOURCE,name.startswith('clamped_')))
            for leaf in ['library.spice','bench.cir','bench.cir.prn','summary.json']:
                (folder/leaf).write_text('{}')
            results.append(dict(task=name,receiver_transport=dict(missing_output_edges=0,
                pulses=[dict(output_edges_in_next_input_period=1)])))
        (screen/'manifest.json').write_text(json.dumps(dict(tasks=tasks)))
        (screen/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,results=results)))
        return screen

    def test_exact_source_proofs_include_all_three_controls(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);screen=self.fixture(root)
            with patch.object(physical,'ROOT',root),patch.object(physical,'recheck') as recheck:
                proof=physical.source_gate(screen)
            recheck.assert_called_once_with(screen)
            self.assertEqual(len(proof),17)
            self.assertTrue(all(len(value)==64 for value in proof.values()))

    def test_original_strong_clamp_cannot_supply_wide_input_source_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);screen=self.fixture(root,wide=False)
            with patch.object(physical,'ROOT',root),patch.object(physical,'recheck'):
                with self.assertRaisesRegex(ValueError,'another receiver source'):physical.source_gate(screen)

    def test_missing_source_case_holds_before_remeasurement(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);screen=self.fixture(root)
            (screen/'clamped_sharp_control/summary.json').unlink()
            with patch.object(physical,'ROOT',root),patch.object(physical,'recheck') as recheck:
                with self.assertRaisesRegex(ValueError,'Complete all'):physical.source_gate(screen)
            recheck.assert_not_called()

    def test_missing_or_repeated_edges_hold_layout(self):
        for missing,count in [(1,1),(0,2),(0,0)]:
            with self.subTest(missing=missing,count=count),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);screen=self.fixture(root);path=screen/'summary.json'
                summary=json.loads(path.read_text());transport=summary['results'][0]['receiver_transport']
                transport['missing_output_edges']=missing;transport['pulses'][0]['output_edges_in_next_input_period']=count
                path.write_text(json.dumps(summary))
                with patch.object(physical,'ROOT',root),patch.object(physical,'recheck'):
                    with self.assertRaisesRegex(ValueError,'loses or repeats'):physical.source_gate(screen)

    def test_wider_finger_banks_preserved_when_only_clamp_is_repositioned(self):
        _,devices=flatten(circuits(source_variant(SOURCE,True)),'openlvds_receiver_core')
        ordered=physical.place_clamp(devices)
        self.assertEqual({d['name']:d for d in ordered},{d['name']:d for d in devices})
        clamp=lambda d:'__XTRACK__' in d['name'] or d['name'].endswith(('__XCLAMP0','__XCLAMP1','__XCLAMP2','__XCLAMP3'))
        self.assertEqual([d for d in devices if not clamp(d)],[d for d in ordered if not clamp(d)])
        at=next(i for i,d in enumerate(ordered) if '__XIB0__' in d['name'])
        self.assertTrue(all(clamp(d) for d in ordered[at-10:at]))

    def test_native_preparation_rejects_other_variant_or_width(self):
        for variant,width in [('strong',20),('strong',40),('strong_wide_input',20)]:
            with self.subTest(variant=variant,width=width),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);layout=root/'build/diagnostics/receiver_layout/test';layout.mkdir(parents=True)
                identity=dict(input_tail_scale=2,decision_clamped=True,clamp_variant=variant,input_pair_width_um=width)
                (layout/'summary.json').write_text(json.dumps(dict(identity=identity)))
                (layout/'extraction.json').write_text('{}')
                with patch.object(replay,'ROOT',root),patch.object(replay,'engine',return_value='ngspice'),patch.object(replay,'source_gate') as gate:
                    with self.assertRaisesRegex(ValueError,'40 um input-pair'):
                        replay.prepare(root/'build/diagnostics/clock_restore/test',layout)
                gate.assert_not_called()
