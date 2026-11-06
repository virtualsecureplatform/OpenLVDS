# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_regular_regenerated_pvt_v291 as p

class RoutedPvtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Synthetic metadata exercises aggregation only; no native trace is admitted.
        cls.matrix=p.specifications();cls.rows=[]
        for s in cls.matrix:
            delay={(0,0):400,(0,31):800,(1,0):650}[s['coarse'],s['fine']]+{'ff':150,'ss':-150}.get(s['process'],0)
            r={k:True for k in p.NATIVE_FLAGS}
            r.update(whole_bank_rc_retained=True,terminal_stress=[dict(passed=True)]*1529,
                programming_gates=[dict(passed=True)]*173,controls=[dict(passed=True)],
                edge_delays_ps={edge:[delay+k*.1 for k in range(8)] for edge in ('rise','fall')})
            cls.rows.append(dict(spec=s,result=r,error=None))

    def test_complete_405_conditions_reuse_27_and_keep_378_new(self):
        matrix=self.matrix;self.assertEqual(len(matrix),405)
        self.assertEqual(len({json.dumps(s,sort_keys=True) for s in matrix}),405)
        self.assertEqual({(s['process'],s['temperature']) for s in matrix},{(c,t) for c in ('tt','ff','ss','fs','sf') for t in (0,25,40)})
        self.assertEqual({s['frequency_mhz'] for s in matrix},{390,400,410});self.assertEqual({s['duty'] for s in matrix},{.4,.5,.6})
        old=p.source.specifications(p.source.native.spec());self.assertEqual(len([s for s in matrix if s not in old]),378)
        r=p.assess(self.rows,matrix);self.assertTrue(r['sparse_clock_pvt_matrix_passed']);self.assertEqual(len(r['pvt_points']),15)
        self.assertTrue(all(g['cases']==27 for g in r['pvt_points']))
        self.assertFalse(r['dense_common_tables_qualified']);self.assertFalse(r['whole_clock_qualified']);self.assertFalse(r['qualified_phy'])
        # Different PVT delay offsets must not invent a cross-PVT overlap requirement.
        self.assertTrue(all(g['conservative_coarse_overlap_ps']['rise']>149 for g in r['pvt_points']))

    def test_missing_duplicate_wrong_clock_or_failed_case_cannot_pass(self):
        self.assertIsNone(p.assess(self.rows[:-1],self.matrix))
        bad=list(self.rows);bad[-1]=bad[0]
        with self.assertRaisesRegex(ValueError,'405 unique'):p.assess(bad,self.matrix)
        bad=list(self.rows);bad[0]=dict(bad[0],error='native engine failed')
        self.assertIsNone(p.assess(bad,self.matrix))
        bad=deepcopy(self.rows);bad[0]['spec']['frequency_mhz']=420
        with self.assertRaises(ValueError):p.assess(bad,self.matrix)

    def test_every_native_flag_terminal_gate_control_and_history_remains_required(self):
        base=self.rows[0]['result']
        for flag in p.NATIVE_FLAGS:
            self.assertFalse(p.point_passed(dict(base,**{flag:False})),flag)
        for field in ('terminal_stress','programming_gates','controls'):
            bad=deepcopy(base);bad[field][0]['passed']=False;self.assertFalse(p.point_passed(bad),field)
        for value in (float('nan'),float('inf'),-1):
            bad=deepcopy(base);bad['edge_delays_ps']['rise'][0]=value;self.assertFalse(p.point_passed(bad))
        bad=deepcopy(base);bad['edge_delays_ps']['fall'].pop();self.assertFalse(p.point_passed(bad))
        self.assertFalse(p.point_passed(dict(base,whole_bank_rc_retained=False)))

    def test_positive_average_does_not_hide_history_overlap_or_progression_failure(self):
        rows=deepcopy(self.rows)
        target=next(r for r in rows if r['spec']['process']=='tt' and r['spec']['temperature']==25 and r['spec']['coarse']==1)
        target['result']['edge_delays_ps']['rise'][0]=810
        r=p.assess(rows,self.matrix);self.assertFalse(r['sparse_clock_pvt_matrix_passed'])
        failed=[g for g in r['pvt_points'] if not g['sparse_clock_pvt_point_passed']]
        self.assertEqual([(g['process'],g['temperature']) for g in failed],[('tt',25)])
        rows=deepcopy(self.rows)
        next(r for r in rows if r['spec']['coarse']==r['spec']['fine']==0)['result']['edge_delays_ps']['rise']=[900]*8
        self.assertFalse(p.assess(rows,self.matrix)['sparse_clock_pvt_matrix_passed'])

    def test_all_fixture_conditions_keep_native_input_solver_load_and_supplies(self):
        i=dict(top='native_bank',ports=['IN','OUT','VPWR','VGND'],model='model.lib',observations=dict(devices=[],controls=[]))
        for s in self.matrix:
            text=p.fixture(Path('/unused-fixture'),i,s)
            self.assertIn('.lib "model.lib" '+s['process'],text);self.assertIn('temp='+str(s['temperature']),text)
            self.assertEqual(text.count('tanh('),16);self.assertIn('.tran 2p 25n 0 2p',text)
            self.assertIn('method=gear reltol=1e-4 abstol=1e-12',text)
            self.assertEqual(text.replace('OpenLVDS '+p.VERSION,'OpenLVDS '+p.source.VERSION,1),p.source.fixture(Path('/unused-fixture'),i,s))

    def test_incomplete_pilot_cannot_create_pvt_manifest_or_submit_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);(parent/'state.json').write_text(json.dumps(dict(status='running',qualified_phy=False)))
            (parent/'summary.json').write_text(json.dumps(dict(rows=[])))
            with self.assertRaisesRegex(ValueError,'27-case'):p.require_pilot(parent,dict(tasks=[],identity=dict(specs=[])))
        with patch.object(p.source,'bound',side_effect=ValueError('native physical prerequisite absent')):
            with self.assertRaises(ValueError):p.prepare(Path('/not-an-admitted-bank'))

if __name__=='__main__':unittest.main()
