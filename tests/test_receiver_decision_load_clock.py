# SPDX-License-Identifier: GPL-3.0-only
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_decision_load_clock as clock


class DecisionLoadClock(unittest.TestCase):
    def test_source_admission_requires_every_control_and_original_edge_once(self):
        summary=dict(diagnostic_complete=True,results=[dict(task=n,receiver_transport=dict(missing_output_edges=0,
            pulses=[dict(output_edges_in_next_input_period=1) for _ in range(47)])) for n in sorted(clock.CASES)])
        self.assertTrue(clock.admitted(summary))
        self.assertFalse(clock.admitted(dict(summary,results=summary['results'][:-1])))
        self.assertFalse(clock.admitted(dict(summary,results=[summary['results'][0]]*3)))
        for count in [0,2]:
            changed=copy.deepcopy(summary)
            changed['results'][0]['receiver_transport']['pulses'][0]['output_edges_in_next_input_period']=count
            self.assertFalse(clock.admitted(changed))
        changed=copy.deepcopy(summary);changed['results'][0]['receiver_transport']['pulses'].pop()
        self.assertFalse(clock.admitted(changed))

    def template(self,root):
        base=root/'build/diagnostics/receiver_clamp/template';base.mkdir(parents=True)
        tasks=[]
        for name in sorted(clock.CASES):
            folder=base/name;folder.mkdir()
            values={'candidate.spice':'* exact unchanged source\n','library.spice':'* exact unchanged library\n',
                'bench.cir':f'Title\n.include "{folder}/library.spice"\n.tran 5p 80n 0 5p\n.print tran V(Q)\n.end\n'}
            for n,text in values.items():(folder/n).write_text(text)
            tasks.append(dict(id=name,clamped=name.startswith('clamped'),files={n:clock.digest(folder/n) for n in values}))
        manifest=dict(identity=dict(inputs={},code={clock.NAME:clock.digest(Path(clock.__file__))}),tasks=tasks)
        (base/'manifest.json').write_text(json.dumps(manifest));return base

    def test_exact_three_circuits_and_observations_retained_with_only_numerical_and_path_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=self.template(root);screen=root/'build/diagnostics/receiver_decision_load_matrix/dc'
            with patch.object(clock,'ROOT',root):
                out=clock.derive(base,screen,{'dc/proof':'sha'})
                manifest=json.loads((out/'manifest.json').read_text())
                self.assertEqual(len(manifest['tasks']),3)
                for task in manifest['tasks']:
                    old=base/task['id'];new=out/task['id']
                    for name in ['candidate.spice','library.spice']:self.assertEqual((old/name).read_bytes(),(new/name).read_bytes())
                    expected=(old/'bench.cir').read_text().replace(str(old/'library.spice'),str(new/'library.spice')).replace('0 5p','0 1p')
                    self.assertEqual((new/'bench.cir').read_text(),expected)
                self.assertEqual(manifest['identity']['inputs']['dc/proof'],'sha')
                before=(out/'manifest.json').read_bytes();self.assertEqual(clock.derive(base,screen,{'dc/proof':'sha'}),out)
                self.assertEqual((out/'manifest.json').read_bytes(),before)

    def test_changed_template_or_incomplete_coverage_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=self.template(root);screen=root/'dc'
            with patch.object(clock,'ROOT',root):
                (base/sorted(clock.CASES)[0]/'candidate.spice').write_text('changed')
                with self.assertRaisesRegex(ValueError,'fixture changed'):clock.derive(base,screen,{})
                manifest=json.loads((base/'manifest.json').read_text());manifest['tasks'].pop()
                (base/'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError,'three original'):clock.derive(base,screen,{})

    def test_incomplete_dc_never_prepares_clock_simulations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);screen=root/'build/diagnostics/receiver_decision_load_matrix/dc';screen.mkdir(parents=True)
            (screen/'manifest.json').write_text(json.dumps(dict(identity=dict(children=[dict(root='missing')]*15))))
            with patch.object(clock,'ROOT',root),patch.object(clock.factory,'prepare') as prepare,patch.object(clock.dc,'run') as run:
                with self.assertRaisesRegex(ValueError,'Complete all fifteen'):clock.prepare(root/'parent',screen)
                prepare.assert_not_called();run.assert_not_called()

    def test_failed_complete_dc_cannot_admit_clock_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);screen=root/'build/diagnostics/receiver_decision_load_matrix/dc';screen.mkdir(parents=True)
            child=root/'child';child.mkdir();(child/'summary.json').write_text('{}')
            (screen/'manifest.json').write_text(json.dumps(dict(identity=dict(children=[dict(root='child')]*15))))
            (screen/'summary.json').write_text('{}')
            with patch.object(clock,'ROOT',root),patch.object(clock.dc,'run',return_value=dict(dc_all_passed=False,required=15)),patch.object(clock.factory,'prepare') as prepare:
                with self.assertRaisesRegex(ValueError,'must pass'):clock.prepare(root/'parent',screen)
                prepare.assert_not_called()


if __name__=='__main__':unittest.main()
