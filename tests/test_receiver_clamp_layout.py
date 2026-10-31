# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_receiver_clamp_candidate as candidate
from layout import circuits,flatten
from receiver_clamp_experiment import source_variant,TOP
ROOT=Path(__file__).resolve().parents[1]


class ReceiverClampLayout(unittest.TestCase):
    def test_only_added_devices_move_and_every_terminal_is_preserved(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        _,baseline=flatten(circuits(source_variant(source,False)),TOP)
        _,clamped=flatten(circuits(source_variant(source,True)),TOP)
        result=candidate.place_clamp(clamped)
        self.assertEqual({d['name']:d for d in result},{d['name']:d for d in clamped})
        self.assertEqual([d for d in result if d in baseline],baseline)
        first=next(i for i,d in enumerate(result) if '__XIB0__' in d['name'])
        self.assertEqual(len([d for d in result[first-4:first] if d not in baseline]),4)

    def test_unexpected_clamp_topology_is_rejected(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        _,devices=flatten(circuits(source_variant(source,False)),TOP)
        with self.assertRaisesRegex(ValueError,'topology'):candidate.place_clamp(devices)

    def test_pending_source_screen_cannot_launch_a_replay_or_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);screen=root/'build/diagnostics/receiver_clamp/pending';screen.mkdir(parents=True)
            with patch.object(candidate,'ROOT',root),patch.object(candidate,'recheck') as recheck,\
                 patch.object(candidate.physical,'build') as build:
                with self.assertRaisesRegex(ValueError,'Complete all'):candidate.build(screen)
            recheck.assert_not_called();build.assert_not_called()

    def test_failed_clamped_cadence_cannot_reach_physical_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);screen=root/'build/diagnostics/receiver_clamp/failed';screen.mkdir(parents=True)
            tasks=[dict(id=n) for n in sorted(candidate.CASES)]
            (screen/'manifest.json').write_text(json.dumps(dict(tasks=tasks)))
            results=[dict(task=n,receiver_transport=dict(missing_output_edges=2 if n=='clamped_captured' else 0))
                     for n in sorted(candidate.CASES)]
            (screen/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,results=results)))
            for name in candidate.CASES:
                (screen/name).mkdir();(screen/name/'summary.json').write_text('{}')
            with patch.object(candidate,'ROOT',root),patch.object(candidate,'recheck') as recheck,\
                 patch.object(candidate.physical,'build') as build:
                with self.assertRaisesRegex(ValueError,'still loses clock edges'):candidate.build(screen)
            recheck.assert_called_once_with(screen);build.assert_not_called()

    def test_passing_screen_for_another_resistor_cannot_qualify_this_layout(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'analog').mkdir();(root/'analog/openlvds.spice').write_text(source)
            screen=root/'build/diagnostics/receiver_clamp/other';screen.mkdir(parents=True)
            (screen/'manifest.json').write_text(json.dumps(dict(tasks=[dict(id=n) for n in candidate.CASES])))
            results=[dict(task=n,receiver_transport=dict(missing_output_edges=0)) for n in candidate.CASES]
            (screen/'summary.json').write_text(json.dumps(dict(diagnostic_complete=True,results=results)))
            for name in candidate.CASES:
                folder=screen/name;folder.mkdir();(folder/'summary.json').write_text('{}')
                text=source_variant(source,name.startswith('clamped_'))
                if name=='clamped_captured':
                    text=text.replace('XCLAMP0 CO CO_TRACK VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=1.25',
                                      'XCLAMP0 CO CO_TRACK VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=2.5')
                (folder/'candidate.spice').write_text(text)
            with patch.object(candidate,'ROOT',root),patch.object(candidate,'recheck'),\
                 patch.object(candidate.physical,'build') as build:
                with self.assertRaisesRegex(ValueError,'another receiver source'):candidate.build(screen)
            build.assert_not_called()
