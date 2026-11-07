# SPDX-License-Identifier: GPL-3.0-only
"""Guard full PVT coverage, exact retained evidence and unchanged native protocol."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
try:
    import probe_routed_counter_pvt_v354 as p
except ModuleNotFoundError as error:
    if error.name not in ('klayout','numpy'):raise
    p=None


@unittest.skipIf(p is None,'requires project counter-physical Python with NumPy and KLayout')
class RoutedCounterPVTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((p.PARENT/'manifest.json').read_text())
        cls.rows=json.loads((p.PARENT/'summary.json').read_text())['rows']
        cls.devices=cls.manifest['identity']['devices'][p.pilot.VARIANT]
        cls.receipts=[json.loads((ROOT/'build/reports/local_setter_shared_rc_native_replay'/stamp/'summary.json').read_text())
            for stamp in ('20261107T111442Z','20261107T114608Z','20261107T115850Z','20261107T120227Z')]

    def test_exact_270_pvt_clock_duty_stop_product_without_supply_sweep(self):
        specs=p.specifications()
        actual={(s['process'],s['temperature'],s['mhz'],s['duty'],s['stop_level']) for s in specs}
        expected={(c,t,f,d,l) for c in ('tt','ff','ss','fs','sf') for t in (0,25,40)
                  for f in (390,400,410) for d in (.4,.5,.6) for l in (0,1)}
        self.assertEqual(actual,expected);self.assertEqual(len(specs),270)
        self.assertTrue(all(s['input_slew_ps']==100 and s['buffer_variant']=='request_taper' for s in specs))

    def test_twelve_verified_traces_are_retained_and_258_are_fresh(self):
        tasks=p.tasks(ROOT/'build/unused-pvt-test',self.devices,self.manifest)
        retained=[t for t in tasks if t['mode']=='retained']
        self.assertEqual(len(retained),12)
        self.assertEqual(len([t for t in tasks if t['mode']=='simulate']),258)
        self.assertEqual({t['source_case'] for t in retained},
                         {str((p.PARENT/str(k)).relative_to(ROOT)) for k in range(12)})
        for task in retained:
            old=self.manifest['tasks'][int(Path(task['source_case']).name)]
            self.assertEqual(task['spec'],old['spec']);self.assertEqual(task['deck_sha256'],old['deck_sha256'])

    def test_all_twelve_replays_are_required_with_bound_raw_and_exact_samples(self):
        inputs=p.replay_coverage(self.receipts,self.manifest,self.rows)
        self.assertTrue(all(str((p.PARENT/str(k)/'bench.raw').relative_to(ROOT)) in inputs for k in range(12)))
        with self.assertRaises(ValueError):p.replay_coverage(self.receipts[:-1],self.manifest,self.rows)
        with self.assertRaises(ValueError):p.replay_coverage(self.receipts+[self.receipts[0]],self.manifest,self.rows)
        broken=deepcopy(self.receipts)
        broken[-1]['rows'][0]['exact_limiting_samples']['whole_counter']['peak_v']+=.001
        with self.assertRaises(ValueError):p.replay_coverage(broken,self.manifest,self.rows)
        broken=deepcopy(self.receipts)
        del broken[-1]['inputs'][str((p.PARENT/'11/bench.raw').relative_to(ROOT))]
        with self.assertRaises(ValueError):p.replay_coverage(broken,self.manifest,self.rows)

    def test_full_original_protocol_and_native_models_are_kept_for_every_pvt(self):
        for process in ('tt','ff','ss','fs','sf'):
            for mhz in (390,400,410):
                spec=dict(p.specifications()[0],process=process,temperature=25,mhz=mhz)
                text=p.fixture(ROOT/'build/unused-pvt-test/0',spec,self.devices)
                self.assertIn('" '+process+'\n',text)
                self.assertIn('.options device temp=25',text)
                self.assertIn('VDD VDD 0 1.8',text)
                self.assertIn('.options timeint method=gear reltol=1e-4 abstol=1e-12',text)
                self.assertIn('.tran 1p 26n 0 1p',text.splitlines())
                self.assertNotIn('.ic ',text)
                self.assertIn('V(XD:XR:low0',text)

    def test_partial_or_one_failed_point_cannot_pass_counter_pvt(self):
        tasks=p.tasks(ROOT/'build/unused-pvt-test',self.devices,self.manifest)
        result=self.rows[0]['result']
        rows=[dict(task=t,error=None,result=result) for t in tasks]
        self.assertTrue(p.assess(rows)['routed_counter_pvt_boundary_screen_passed'])
        self.assertFalse(p.assess(rows)['qualified_phy'])
        self.assertIsNone(p.assess(rows[:-1]))
        rows[-1]=dict(rows[-1],result=dict(result,terminal_screen_passed=False))
        self.assertFalse(p.assess(rows)['routed_counter_pvt_boundary_screen_passed'])


if __name__=='__main__':unittest.main()
