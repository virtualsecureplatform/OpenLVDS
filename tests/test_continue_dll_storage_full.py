# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_dll_storage_full as handoff


class FullStorageHandoff(unittest.TestCase):
    def qualification(self,root):
        q=root/'build/diagnostics/dll_qualification/test';q.mkdir(parents=True)
        m=dict(identity=dict(full_models=dict(inputs={'dll':'fixed'})),tasks=[dict(id='case_'+str(i)) for i in range(336)],comparisons=[dict(full='a',fast='b')])
        (q/'manifest.json').write_text(json.dumps(m))
        (q/'summary.json').write_text(json.dumps(dict(passed=True,manifest_sha256=handoff.sha(q/'manifest.json'),tasks={t['id']:dict(status='passed') for t in m['tasks']},dll_full_fast_comparisons=[dict(passed=True)])))
        return q

    def test_full_native_requires_every_case_and_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=self.qualification(Path(tmp));good=json.loads((q/'summary.json').read_text());self.assertTrue(handoff.full_native(q)['passed'])
            for kind in ['missing','failed','comparison','stale']:
                r=deepcopy(good)
                if kind=='missing':r['tasks'].pop('case_335')
                elif kind=='failed':r['tasks']['case_335']['status']='failed'
                elif kind=='comparison':r['dll_full_fast_comparisons'][0]['passed']=False
                else:r['manifest_sha256']='changed'
                (q/'summary.json').write_text(json.dumps(r))
                with self.assertRaises(ValueError):handoff.full_native(q)

    def test_screen_report_must_belong_to_exact_qualification_and_pass(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)):
            root=Path(tmp);q=self.qualification(root);p=q/'stability_screen/test/summary.json';p.parent.mkdir(parents=True);p.write_text('{}')
            row=dict(stability_screen_passed=True,qualification=str(q.relative_to(root)),report=str(p.relative_to(root)),report_sha256=handoff.sha(p))
            self.assertEqual(handoff.screen_receipt(q,row),p)
            with self.assertRaises(ValueError):handoff.screen_receipt(q,dict(row,stability_screen_passed=False))
            with self.assertRaises(ValueError):handoff.screen_receipt(q,dict(row,qualification='another'))
            p.write_text('{"changed":true}')
            with self.assertRaises(ValueError):handoff.screen_receipt(q,row)

    def all_pvt(self,q):
        req=dict(process_corners=['tt','ff','ss','fs','sf'],temperatures_c=[0,25,40]);(q/'requirements.json').write_text(json.dumps(req));(q/'full.spice').write_text('fixed model')
        p=q/'stability_all_pvt/test/summary.json';p.parent.mkdir(parents=True)
        (p.parent/'manifest.json').write_text(json.dumps(dict(qualification_manifest_sha256=handoff.sha(q/'manifest.json'),library_sha256=handoff.sha(q/'full.spice'))))
        corner=lambda c:dict(corner=c,passed=True,models=[dict(passed=True,model_valid=True,phase_margin_min_deg=65,gain_margin_min_db=8) for _ in range(3)],transient_validation=[dict(target_mhz=m,passed=True,amplitude_relative_error=.1,settling_relative_error=.1) for m in [390,410]])
        r=dict(passed=True,all_pvt=True,full_inputs={'dll':'fixed'},manifest_sha256=handoff.sha(p.parent/'manifest.json'),results=[corner(f'{proc}_{t}') for proc in req['process_corners'] for t in req['temperatures_c']]);p.write_text(json.dumps(r));return p,r

    def test_all_fifteen_corners_margins_and_steps_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=self.qualification(Path(tmp));p,good=self.all_pvt(q);self.assertTrue(handoff.all_pvt(q,p)['passed'])
            for kind in ['missing','duplicate','margin','gain','nan_margin','step','model']:
                r=deepcopy(good)
                if kind=='missing':r['results'].pop()
                elif kind=='duplicate':r['results'][-1]=deepcopy(r['results'][0])
                elif kind=='margin':r['results'][-1]['models'][0]['phase_margin_min_deg']=59
                elif kind=='gain':r['results'][-1]['models'][0]['gain_margin_min_db']=5
                elif kind=='nan_margin':r['results'][-1]['models'][0]['phase_margin_min_deg']=float('nan')
                elif kind=='step':r['results'][-1]['transient_validation'][0]['settling_relative_error']=.26
                else:r['full_inputs']={'dll':'different'}
                p.write_text(json.dumps(r))
                with self.assertRaises(ValueError):handoff.all_pvt(q,p)

    def test_prior_resource_context_is_retained_without_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(handoff,'ROOT',Path(tmp)),patch.object(handoff.subprocess,'run') as run:
            out=Path(tmp)/'build/diagnostics/dll_storage_full_followup/old';out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(dict(identity=dict(max_native_workers=3,no_outer_lease=True,files={}))))
            (out/'state.json').write_text('retained')
            with self.assertRaisesRegex(ValueError,'Prior full-DLL'):handoff.run(out)
            self.assertEqual((out/'state.json').read_text(),'retained');run.assert_not_called()
