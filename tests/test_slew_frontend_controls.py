from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_slew_frontend_controls as control


class SourceFrontendControls(unittest.TestCase):
    def data(self):
        req=json.loads((control.ROOT/'requirements.json').read_text())
        variants=['clkbuf_4','clkbuf_8'];tasks=control.expansion.tasks(req,variants)
        m=dict(tasks=tasks)
        r=dict(ranked_survivors=variants,candidates=[dict(variant=v,passed=True,worst_screened_pvt=w) for v,w in zip(variants,[['ss',40],['fs',25]])],
               results=[dict(task=t['id'],result={'phase':{'filtered_area_difference_v':t['spec']['offset_ps']*.0007}}) for t in tasks])
        return m,r

    def test_all_pvt_matched_extreme_slews_and_deduplicated_frequency_extremes(self):
        m,r=self.data();tasks=control.task_plan(r,m)
        self.assertEqual(len(tasks),57+63);self.assertEqual(len({t['id'] for t in tasks}),len(tasks))
        for variant,worst in [('clkbuf_4',('ss',40)),('clkbuf_8',('fs',25))]:
            group=[t for t in tasks if t['variant']==variant]
            for p,t,f in control.points(worst):
                self.assertEqual({(q['spec']['reference_slew_ps'],q['spec']['feedback_slew_ps']) for q in group if (q['spec']['process'],q['spec']['temperature'],q['spec']['mhz'])==(p,t,f)}, {(100,100),(20,200),(200,20)})
            self.assertTrue(all(t['area_limits_v'][0]<0<t['area_limits_v'][1] for t in group))

    def test_invalid_worst_missing_donor_or_unbalanced_source_cannot_prepare_controls(self):
        with self.assertRaises(ValueError):control.points(('ss',85))
        m,r=self.data();m['tasks']=[t for t in m['tasks'] if not (t['variant']=='clkbuf_4' and t['spec']['offset_ps']==0)]
        with self.assertRaises(ValueError):control.task_plan(r,m)
        m,r=self.data();r['ranked_survivors']=[]
        with self.assertRaises(ValueError):control.task_plan(r,m)
        m,r=self.data()
        for row in r['results']:row['result']['phase']['filtered_area_difference_v']+=1
        with self.assertRaises(ValueError):control.task_plan(r,m)

    def test_a_failed_control_candidate_is_filtered_without_reordering_source_rank(self):
        m,r=self.data();tasks=control.task_plan(r,m);manifest=dict(tasks=tasks,identity={'variants':r['ranked_survivors']})
        rows=[dict(task=t['id'],variant=t['variant'],spec=t['spec'],error=None,result={'passed':True}) for t in tasks]
        self.assertEqual(control.aggregate(manifest,rows)['ranked_survivors'],r['ranked_survivors'])
        rows[0]['result']['passed']=False;report=control.aggregate(manifest,rows)
        self.assertEqual(report['ranked_survivors'],['clkbuf_8']);self.assertTrue(report['source_controls_passed']);self.assertFalse(report['physical_admission'])
        for row in rows:row['error']='incomplete';row['result']=None
        self.assertFalse(control.aggregate(manifest,rows)['source_controls_passed'])
        with self.assertRaises(ValueError):control.aggregate(manifest,rows[:-1])
        with self.assertRaises(ValueError):control.aggregate(manifest,rows+[rows[0]])

    def test_failed_baseline_gate_and_partial_campaign_do_not_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(control.baseline,'verify',return_value={'baseline_protocol_passed':False}),self.assertRaises(ValueError):control.prepare(root/'e',root/'baseline')
            self.assertEqual(list(root.iterdir()),[])
            (root/'manifest.json').write_text('{}');(root/'state.json').write_text('{}')
            with patch.object(control,'bound',return_value={'identity':{'parent':'unused'},'tasks':[]}),patch.object(control,'lease') as lease:
                with self.assertRaisesRegex(ValueError,'no retry'):control.run(root)
                lease.assert_not_called()

    def test_control_clock_and_phase_recovery_are_independent_admission_requirements(self):
        names=['REF','FDB','REF_FAST','FDB_FAST','RST','ENABLE',
               'REF_FF_CLK_0','REF_FF_CLK_1','FB_FF_CLK_0','FB_FF_CLK_1']
        task=dict(spec={'mhz':400},aliases={n:n for n in names},area_limits_v=[-.01,.01])
        wave=np.zeros((2,len(names)+2));header={'V('+n+')':j+2 for j,n in enumerate(names)}
        for failure in (None,'phase','controls','transport','recovery'):
            phase=dict(passed=failure!='phase',phase={'filtered_area_difference_v':.02 if failure=='recovery' else 0.})
            with self.subTest(failure=failure),patch.object(control.expansion.screen,'measure',return_value=phase), \
                 patch.object(control.expansion.screen.cal.old,'completed',return_value=(wave,dict(header))), \
                 patch.object(control.protocol,'measure',return_value={'passed':failure!='controls'}) as protocol, \
                 patch.object(control.baseline.phase,'gate_transport',return_value={'passed':failure!='transport'}):
                result=control.measure(Path('unused'),task)
                self.assertEqual(result['passed'],failure is None)
                self.assertEqual(set(protocol.call_args.args[3]),set(names)-{'RST','ENABLE'})
