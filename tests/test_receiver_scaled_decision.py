# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_scaled_decision_experiment as experiment
from layout import circuits

ROOT=Path(__file__).resolve().parents[1]


class ScaledDecision(unittest.TestCase):
    def test_uniform_scaling_preserves_every_other_device_and_all_five_ratios(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        control=experiment.source_variant(source,False);scaled=experiment.source_variant(source,True)
        original=circuits(control);actual=circuits(scaled)
        self.assertEqual(set(original),set(actual))
        for top in original:
            if top!=experiment.TOP:self.assertEqual(original[top],actual[top])
        self.assertEqual(original[experiment.TOP][0],actual[experiment.TOP][0])
        before={r[0]:r for r in original[experiment.TOP][1]};after={r[0]:r for r in actual[experiment.TOP][1]}
        self.assertEqual(set(before),set(after))
        changed=[]
        for name,row in before.items():
            if name in experiment.WIDTHS:
                self.assertEqual(after[name],(row[0],row[1],row[2],dict(row[3],w=experiment.WIDTHS[name][1])))
                self.assertEqual(float(after[name][3]['w'])/float(row[3]['w']),4)
                changed.append(name)
            else:self.assertEqual(after[name],row)
        self.assertEqual(set(changed),set(experiment.WIDTHS))
        self.assertEqual(after['XCT'][3]['w'],'64')
        self.assertFalse(any(n.startswith('XCLAMP') for n in after))

    def test_cannot_rescale_or_substitute_wrong_tail_pair_mirror_or_connectivity(self):
        control=experiment.source_variant((ROOT/'analog/openlvds.spice').read_text(),False)
        for altered in [experiment.scale_decision(control),control.replace('w=16 l=0.5','w=64 l=0.5'),
                control.replace('XC0 CL PN CT VSS','XC0 CL PP CT VSS'),
                control.replace('XCM CO CL VDDD VDDD','XCM CO CO VDDD VDDD')]:
            with self.assertRaisesRegex(ValueError,'exact unclamped'):experiment.scale_decision(altered)

    def test_missing_control_cannot_launch_original_simulator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'build/diagnostics/receiver_tail_headroom_static/missing';parent.mkdir(parents=True)
            with patch.object(experiment,'ROOT',root),patch.object(experiment,'engine',return_value='ngspice'),patch.object(experiment.control,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete the reduced-tail control'):experiment.prepare(parent)
                run.assert_not_called()


if __name__=='__main__':unittest.main()
