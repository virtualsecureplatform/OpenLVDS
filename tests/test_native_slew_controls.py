from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import qualify_native_slew_controls as control


class NativeSlewControls(unittest.TestCase):
    def recipe(self,worst=('ss',40)):
        return dict(version=control.pilot.coverage.VERSION,worst_screened_pvt=list(worst))

    def test_all_pvt_three_slews_and_deduplicated_frequency_points(self):
        for worst,count in [(('ss',40),57),(('tt',25),57),(('fs',25),63)]:
            with self.subTest(worst=worst):
                tasks=control.tasks(self.recipe(worst));self.assertEqual(len(tasks),count)
                self.assertEqual(len({t['id'] for t in tasks}),count)
                for p,t,f in control.source_controls.points(worst):
                    group=[q['spec'] for q in tasks if (q['spec']['process'],q['spec']['temperature'],q['spec']['mhz'])==(p,t,f)]
                    self.assertEqual({(q['reference_slew_ps'],q['feedback_slew_ps']) for q in group},{(100,100),(20,200),(200,20)})
                    self.assertTrue(all(q['kind']=='phase' and q['offset_ps']==0 for q in group))
        for recipe in ({'version':'old','worst_screened_pvt':['ss',40]},self.recipe(('ss',85))):
            with self.assertRaises(ValueError):control.tasks(recipe)

    def test_no_native_controls_before_complete_pilot_and_known_failures_pass(self):
        for passed,restored in [(False,False),(True,False),(False,True)]:
            with tempfile.TemporaryDirectory() as d,patch.object(control,'ROOT',Path(d)):
                root=Path(d);parent=root/'build/diagnostics'/control.pilot.NAMESPACE/'p';parent.mkdir(parents=True)
                with patch.object(control.pilot,'verify',return_value=dict(native_pilot_passed=passed,known_false_bad_cases_restored=restored)), \
                     patch.object(control.pilot,'bound') as bound,self.assertRaisesRegex(ValueError,'must pass'):
                    control.prepare(parent)
                bound.assert_not_called();self.assertFalse((root/'build/diagnostics'/control.NAMESPACE).exists())

    def test_clearance_and_recovered_native_phase_are_both_required(self):
        names=['REF','FDB','RST','ENABLE','REF_FF_CLK_0','REF_FF_CLK_1','FB_FF_CLK_0','FB_FF_CLK_1']
        task=dict(spec={'mhz':410},aliases={n:n for n in names})
        wave=np.zeros((2,len(names)+2));header={'V('+n+')':j+2 for j,n in enumerate(names)}
        for bad in (None,'phase','controls'):
            with self.subTest(bad=bad),patch.object(control.pilot,'measure',return_value={'passed':bad!='phase'}), \
                 patch.object(control.pilot.original,'completed',return_value=(wave,dict(header))), \
                 patch.object(control.protocol,'measure',return_value={'passed':bad!='controls'}) as protocol:
                r=control.measure(Path('unused'),task);self.assertEqual(r['passed'],bad is None)
                self.assertEqual(protocol.call_args.args[2],410)
                self.assertEqual(set(protocol.call_args.args[3]),set(names)-{'RST','ENABLE'})

    def test_all_native_control_results_required_without_phy_admission(self):
        tasks=control.tasks(self.recipe());m=dict(tasks=tasks,identity={'scope':'controls only'})
        rows=[dict(task=t['id'],spec=t['spec'],error=None,result={'passed':True}) for t in tasks]
        report=control.aggregate(m,rows);self.assertTrue(report['native_controls_passed'])
        self.assertFalse(report['physical_admission']);self.assertFalse(report['qualified_phy'])
        rows[0]['result']['passed']=False;self.assertFalse(control.aggregate(m,rows)['native_controls_passed'])
        rows[0]['error']='partial output';rows[0]['result']=None;self.assertFalse(control.aggregate(m,rows)['native_controls_passed'])
        for changed in (rows[:-1],rows+[rows[0]],[] ):
            with self.assertRaises(ValueError):control.aggregate(m,changed)
        changed=deepcopy(rows);changed[0]['spec']['mhz']=500
        with self.assertRaises(ValueError):control.aggregate(m,changed)

    def test_partial_native_controls_do_not_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'manifest.json').write_text('{}');(root/'state.json').write_text('{}')
            with patch.object(control,'bound',return_value={'tasks':[]}),patch.object(control,'lease') as lease:
                with self.assertRaisesRegex(ValueError,'no retry'):control.run(root)
                lease.assert_not_called()
