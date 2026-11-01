# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_lvt_pair_experiment as experiment
from layout import circuits

ROOT=Path(__file__).resolve().parents[1]


class LowThresholdDecisionPair(unittest.TestCase):
    def test_only_two_decision_models_change_with_every_width_and_connection_retained(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        control=experiment.source_variant(source,False);candidate=experiment.source_variant(source,True)
        before=circuits(control);after=circuits(candidate)
        self.assertEqual(set(before),set(after))
        for top in before:
            if top!=experiment.TOP:self.assertEqual(before[top],after[top])
        self.assertEqual(before[experiment.TOP][0],after[experiment.TOP][0])
        old={r[0]:r for r in before[experiment.TOP][1]};new={r[0]:r for r in after[experiment.TOP][1]}
        self.assertEqual(set(old),set(new))
        changed=[]
        for name,row in old.items():
            if name in ['XC0','XC1']:
                self.assertEqual(new[name],(name,row[1],experiment.MODEL,row[3]));changed.append(name)
            else:self.assertEqual(new[name],row)
        self.assertEqual(changed,['XC0','XC1'])
        self.assertEqual(new['XCT'][3],dict(w='16',l='0.5'))
        self.assertFalse(any(name.startswith('XCLAMP') for name in new))

    def test_changed_pair_tail_mirror_or_previously_modified_model_is_refused(self):
        control=experiment.source_variant((ROOT/'analog/openlvds.spice').read_text(),False)
        variants=[experiment.replace_decision_inputs(control),
            control.replace('XC0 CL PN CT VSS','XC0 CL PP CT VSS'),
            control.replace('w=16 l=0.5','w=64 l=0.5'),
            control.replace('XCM CO CL VDDD VDDD','XCM CO CO VDDD VDDD')]
        for source in variants:
            with self.assertRaises(ValueError):experiment.replace_decision_inputs(source)

    def test_missing_completed_control_cannot_call_source_producer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'build/diagnostics/receiver_tail_headroom_static/missing';parent.mkdir(parents=True)
            with patch.object(experiment,'ROOT',root),patch.object(experiment,'engine',return_value='ngspice'),patch.object(experiment.control,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete the reduced-tail control'):experiment.prepare(parent)
                run.assert_not_called()


if __name__=='__main__':unittest.main()
