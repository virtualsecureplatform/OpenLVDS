# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_regular_regenerated_full_range_v301 as p


class FullRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix=p.specifications();cls.rows=[]
        safety=dict(whole_bank_rc_retained=True,terminal_stress=[dict(passed=True)]*1529,
            programming_gates=[dict(passed=True)]*173,controls=[dict(passed=True)])
        for s in cls.matrix:
            code=s['coarse']*32+s['fine'];corner=('tt','ff','ss','fs','sf').index(s['process'])*3+(0,25,40).index(s['temperature'])
            delay=500+code*6+corner*.2
            result=dict(safety,**{flag:True for flag in p.sparse.NATIVE_FLAGS})
            result['edge_delays_ps']={edge:[delay+k*.1 for k in range(8)] for edge in ('rise','fall')}
            cls.rows.append(dict(spec=s,result=result,error=None))

    def test_complete_raw_dimensions_reference_clock_and_fifteen_pvt(self):
        self.assertEqual(len(self.matrix),7680)
        self.assertEqual(len({p.key(s) for s in self.matrix}),7680)
        self.assertEqual({(s['process'],s['temperature']) for s in self.matrix},
            {(x,t) for x in ('tt','ff','ss','fs','sf') for t in (0,25,40)})
        self.assertEqual({(s['coarse'],s['fine']) for s in self.matrix},{(c,f) for c in range(16) for f in range(32)})
        self.assertTrue(all((s['frequency_mhz'],s['duty'],s['cycles'],s['stop_ns'])==(410,.5,8,25) for s in self.matrix))

    def test_native_intervals_feed_common_selector_without_table_or_clock_admission(self):
        r=p.assess(self.rows)
        self.assertTrue(r['all_fifteen_pvt_raw_curves_characterized']);self.assertTrue(r['common_sequence_found'])
        self.assertEqual(len(r['delay_intervals']),7680)
        first=next(x for x in r['delay_intervals'] if x['pvt']=='tt:0' and x['code']==0)
        self.assertEqual(first['edges']['rise'],dict(lo_ps=500,hi_ps=500.7))
        proposal=r['proposed_common_sequence'];self.assertEqual(len(proposal['witnesses']),30)
        self.assertFalse(proposal['native_characterization_verified']);self.assertFalse(proposal['legal_code_table_admitted'])
        for flag in ('all_clock_conditions_characterized','bank_configuration_selected','legal_code_table_admitted',
            'updates_qualified','rx_range_qualified','physical_rom_qualified','whole_clock_qualified','electrical_qualification_passed','qualified_phy'):
            self.assertFalse(r[flag])

    def test_one_corner_range_failure_is_retained_instead_of_selecting_per_corner_orders(self):
        rows=[]
        for original in self.rows:
            row=dict(original);row['result']=dict(original['result'])
            if row['spec']['process']=='sf' and row['spec']['temperature']==40:
                row['result']['edge_delays_ps']={edge:[v+1000 for v in values] for edge,values in original['result']['edge_delays_ps'].items()}
            rows.append(row)
        r=p.assess(rows);self.assertTrue(r['all_native_points_passed']);self.assertFalse(r['common_sequence_found'])
        self.assertEqual(len(r['delay_intervals']),7680)

    def test_missing_duplicate_foreign_clock_and_failed_results_cannot_form_table(self):
        self.assertIsNone(p.assess(self.rows[:-1]))
        rows=list(self.rows);rows[-1]=rows[0]
        with self.assertRaisesRegex(ValueError,'complete unique'):p.assess(rows)
        rows=list(self.rows);rows[0]=dict(rows[0],spec=dict(rows[0]['spec'],duty=.4))
        with self.assertRaises(ValueError):p.assess(rows)
        rows=list(self.rows);rows[0]=dict(rows[0],error='native failure')
        self.assertIsNone(p.assess(rows))

    def test_missing_startup_history_nonfinite_or_safety_failure_prevents_proposal(self):
        for change in (dict(terminal_screen_passed=False),
            dict(edge_delays_ps=dict(rise=[500]*7,fall=[500]*8)),
            dict(edge_delays_ps=dict(rise=[500]*7+[float('nan')],fall=[500]*8))):
            rows=list(self.rows);rows[0]=dict(rows[0],result=dict(rows[0]['result'],**change))
            r=p.assess(rows);self.assertFalse(r['all_native_points_passed']);self.assertIsNone(r['proposed_common_sequence'])

    def test_reuse_exactly_106_matching_cases_and_reject_conflicting_shared_trace(self):
        def item(s):return dict(case='synthetic/'+p.key(s),row=dict(spec=s,result=dict(synthetic=True)))
        sparse=[item(s) for s in p.sparse.specifications()];dense=[item(s) for s in p.dense.specifications()]
        reused=p.reuse(sparse,dense);self.assertEqual(len(reused),106)
        self.assertEqual(len(self.matrix)-len(reused),7574)
        dense=deepcopy(dense);dense[0]['case']='other-native-trace'
        with self.assertRaisesRegex(ValueError,'evidence differs'):p.reuse(sparse,dense)
        with self.assertRaisesRegex(ValueError,'106'):p.reuse(sparse,[])

    def test_full_coarse_boundary_fixtures_preserve_original_native_observations_and_solver(self):
        i=dict(top='native_bank',ports=['IN','OUT','VPWR','VGND'],model='model.lib',observations=dict(devices=[],controls=[]))
        for s in self.matrix:
            if s['process']=='ss' and s['temperature']==40 and s['coarse'] in (0,15) and s['fine'] in (0,31):
                text=p.fixture(Path('/unused'),i,s)
                self.assertEqual(text.replace('OpenLVDS '+p.VERSION,'OpenLVDS '+p.source.VERSION,1),p.source.fixture(Path('/unused'),i,s))
                self.assertEqual(text.count('tanh('),16);self.assertIn('.tran 2p 25n 0 2p',text)
                self.assertIn('method=gear reltol=1e-4 abstol=1e-12',text)

    def test_unadmitted_parent_cannot_create_full_range_artifact(self):
        with patch.object(p.sparse,'bound',side_effect=ValueError('Native prerequisites absent')):
            with self.assertRaises(ValueError):p.prepare(Path('/unadmitted-sparse'),Path('/unadmitted-dense'))

    def test_parent_consumption_remeasures_original_and_inherited_metrics_and_rejects_changed_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'donor';origin=root/'periodic';parent.mkdir();origin.mkdir();rows=[]
            for base,index in ((origin,'0'),(parent,'1')):
                case=base/index;case.mkdir()
                for name in ('bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'):
                    (case/name).write_text('synthetic boundary test '+name)
                task=dict(id=index,spec=dict(code=index),deck_sha256=p.sha(case/'bench.cir'))
                row=dict(task=task,spec=task['spec'],result=dict(value=index),error=None,
                    files={f.name:p.sha(f) for f in case.iterdir()})
                (case/'summary.json').write_text(json.dumps(row));rows.append(row)
            report=dict(inherited_rows=rows[:1],rows=rows[1:],comparison=dict(synthetic=True))
            identity=dict(inherited_rows=rows[:1],matrix=[r['spec'] for r in rows],parent='periodic',inputs={})
            module=SimpleNamespace(bound=Mock(return_value=dict(identity=identity,tasks=[rows[1]['task']])),
                assess=Mock(return_value=report['comparison']),measure=Mock(return_value=rows[1]['result']))
            with patch.object(p,'ROOT',root),patch.object(p.source,'bound',return_value=dict(identity={})),\
                patch.object(p.source,'measure',return_value=rows[0]['result']) as inherited_measure:
                _,consumed,_=p.completed_parent(parent,module,lambda _:report)
                self.assertEqual(len(consumed),2);inherited_measure.assert_called_once();module.measure.assert_called_once()
                module.measure.return_value=dict(value='wrong')
                with self.assertRaisesRegex(ValueError,'metrics do not reproduce'):p.completed_parent(parent,module,lambda _:report)
                module.measure.return_value=rows[1]['result'];(parent/'1/bench.raw').write_text('changed')
                with self.assertRaisesRegex(ValueError,'trace changed'):p.completed_parent(parent,module,lambda _:report)

    def test_per_lease_runtime_guard_checks_sources_bank_pdk_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'scripts').mkdir();out=root/'out';out.mkdir()
            paths=[root/'scripts/runtime.py',root/'model.lib',root/'cad',out/'bank.spice',out/'manifest.json']
            for path in paths:path.write_text('original')
            i=dict(inputs={'scripts/runtime.py':p.sha(paths[0])},pdk_files={str(paths[1]):p.sha(paths[1])},
                cad=dict(sha256=p.sha(paths[2])),simulator=dict(pinned=True))
            manifest=dict(identity=i,bank_sha256=p.sha(paths[3]));digest=p.sha(paths[4])
            with patch.object(p,'ROOT',root),patch.object(p.source.native,'CAD',str(paths[2])),\
                patch.object(p.source.zero,'engine',return_value='ngspice'),\
                patch.object(p.source.zero,'provenance',return_value=i['simulator']):
                p.execution_bound(out,manifest,digest)
                for path in paths:
                    path.write_text('changed')
                    with self.assertRaisesRegex(ValueError,'runtime sources or models changed'):p.execution_bound(out,manifest,digest)
                    path.write_text('original')


if __name__=='__main__':unittest.main()
