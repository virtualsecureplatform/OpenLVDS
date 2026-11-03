from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pilot_native_slew_dll as pilot


class NativeSlewPilot(unittest.TestCase):
    def rows(self):
        return [dict(task=t['id'],spec=t['spec'],error=None,result=dict(passed=True,phase={'filtered_area_difference_v':t['spec']['offset_ps']*.0007})) for t in pilot.tasks()]

    def test_both_known_failures_run_first_and_both_directions_have_every_control(self):
        tasks=pilot.tasks();self.assertEqual(len(tasks),18);self.assertEqual(len({t['id'] for t in tasks}),18)
        self.assertEqual([(t['spec']['reference_slew_ps'],t['spec']['feedback_slew_ps'],t['spec']['offset_ps']) for t in tasks[:2]],[(20,200,50),(200,20,-50)])
        for pair in pilot.coverage.SLEWS:
            self.assertEqual({t['spec']['offset_ps'] for t in tasks if (t['spec']['reference_slew_ps'],t['spec']['feedback_slew_ps'])==pair},set(pilot.coverage.SOURCE_OFFSETS))

    def test_individual_success_cannot_hide_bias_or_nonmonotonic_area_response(self):
        rows=self.rows();good=pilot.aggregate(rows)
        self.assertTrue(good['native_pilot_passed']);self.assertTrue(good['known_false_bad_cases_restored']);self.assertFalse(good['qualified_phy'])
        biased=deepcopy(rows)
        for r in biased:r['result']['phase']['filtered_area_difference_v']+=.04
        self.assertFalse(pilot.aggregate(biased)['native_pilot_passed'])
        rows[0]['result']['phase']['filtered_area_difference_v']=1
        self.assertFalse(pilot.aggregate(rows)['native_pilot_passed'])
        rows=self.rows();rows[0]['result']=None;rows[0]['error']='incomplete'
        self.assertFalse(pilot.aggregate(rows)['known_false_bad_cases_restored'])

    def test_missing_duplicate_or_changed_case_metadata_fails(self):
        rows=self.rows()
        for bad in (rows[:-1],rows+[rows[0]],[dict(rows[0],spec={})]+rows[1:]):
            with self.assertRaises(ValueError):pilot.aggregate(bad)

    def signals(self):
        time=np.linspace(0,160e-9,160001)
        source=.9+.9*np.sin(2*np.pi*400e6*time)
        delayed=.9+.9*np.sin(2*np.pi*400e6*(time-100e-12))
        return time,dict(REF=source,FDB=source,REF_FF_CLK_0=delayed,REF_FF_CLK_1=delayed,FB_FF_CLK_0=delayed,FB_FF_CLK_1=delayed)

    def test_every_gate_has_one_rise_fall_per_cycle_full_swing_and_measured_delay(self):
        time,signals=self.signals();r=pilot.gate_transport(time,signals)
        self.assertTrue(r['passed']);self.assertEqual(len(r['gates']),4)
        for gate in r['gates'].values():
            self.assertAlmostEqual(gate['delivery_delay']['rising']['mean_ps'],100,places=6)
            self.assertAlmostEqual(gate['delivery_delay']['falling']['mean_ps'],100,places=6)
        for bad in [np.full_like(time,.9),np.minimum(signals['REF_FF_CLK_0'],1.1),.9+.9*np.sin(2*np.pi*800e6*time)]:
            values=dict(signals,REF_FF_CLK_1=bad);self.assertFalse(pilot.gate_transport(time,values)['passed'])
        with self.assertRaises(ValueError):pilot.gate_transport(time,{k:v for k,v in signals.items() if not k.startswith('FB_FF_CLK_')})

    def test_failed_model_gate_creates_no_pilot(self):
        with tempfile.TemporaryDirectory() as d,patch.object(pilot.assembly,'verify',side_effect=ValueError('pending physical model')):
            root=Path(d)
            with self.assertRaises(ValueError):pilot.prepare(root/'model')
            self.assertEqual(list(root.iterdir()),[])

    def test_partial_native_pilot_never_dispatches_another_engine(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);(out/'manifest.json').write_text('{}');(out/'state.json').write_text('{}')
            with patch.object(pilot,'bound',return_value={'tasks':[]}),patch.object(pilot,'lease') as lease:
                with self.assertRaisesRegex(ValueError,'no retry'):pilot.run(out)
                lease.assert_not_called()
