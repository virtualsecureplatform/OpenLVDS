from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dll_analog_frontend as policy
import probe_dll_analog_frontend_dc as dc


class AnalogFrontend(unittest.TestCase):
    def values(self,task):
        model,devices=policy.circuit(task['variant'])
        deck,nodes=dc.fixture(task,Path('/fixture'),Path('/pdk/sky130.lib.spice'),
            '.subckt lvds_bias PB NB VDDIO VSS\nR0 PB NB 1k\nR1 NB VSS 1k\n.ends lvds_bias\n'+model)
        values={'v('+n.replace(':','.').lower()+')':0. for n in nodes}
        def v(n,x):values['v('+n.replace(':','.').lower()+')']=x
        v('VDDD',1.8);v('VDDIO',3.3);v('PB',2.3);v('XF:NTAIL',.7);v('XF:VCM',.9)
        v('REF',task['ref_v']);v('FDB',task['fb_v'])
        for side,signal,output in [('XREF',task['ref_v'],'REF_FAST'),('XFB',task['fb_v'],'FDB_FAST')]:
            v('XF:'+side+':T',.25);v('XF:'+side+':L',1.1)
            v('XF:'+side+':O',.2 if signal==0 else 1.8 if signal==1.8 else 1.1)
            v('XF:'+side+':MID',1.8 if signal==0 else 0)
            v(output,0 if signal==0 else 1.8)
        target=policy.VARIANTS[task['variant']]['tail_ua']*1e-6
        for name,vector in policy.op_parameters().items():
            field=name.rsplit('_',1)[-1]
            key=('i('+vector+')') if field=='id' else ('v('+vector+')') if field=='vdsat' else vector
            values[key]={'id':target,'gm':.001,'gds':.000001,'vdsat':.1}[field]
        values.update({'i(va)':-.0005,'i(vd)':-.0004})
        return values,deck

    def test_four_variants_share_reference_and_derive_local_tail_bias(self):
        self.assertEqual(set(policy.VARIANTS),{'tail140_w20','tail140_w40','tail280_w20','tail280_w40'})
        for variant,spec in policy.VARIANTS.items():
            circuit,devices=policy.circuit(variant)
            self.assertEqual(len(devices),20);self.assertEqual(len({d['name'] for d in devices}),20)
            self.assertIn('.subckt '+policy.PAIR+' '+' '.join(policy.PORTS),circuit)
            self.assertIn('XCM VCM VSS sky130_fd_pr__cap_mim_m3_1 w=22 l=22',circuit)
            self.assertIn('XNREF NTAIL NTAIL VSS VSS '+policy.N+' w=100 l=0.3',circuit)
            self.assertIn('XTAIL T NTAIL VSS VSS '+policy.N+' w=100 l=0.3',circuit)
            self.assertIn('XCLK L CLK T VSS',circuit);self.assertIn('XREF O VCM T VSS',circuit)
            mirror=next(d for d in devices if d['name']=='XF:XBIAS:XPM')
            self.assertEqual(mirror['model'],policy.P5);self.assertEqual(mirror['width_um']/2*35,spec['tail_ua'])
            self.assertNotIn('lvds_bias',circuit);self.assertNotIn('\nI',circuit)
        with self.assertRaises(ValueError):policy.circuit('unbounded')

    def test_all_static_states_use_fixed_rails_one_bias_and_no_transient(self):
        self.assertEqual(len(dc.tasks()),20)
        for task in dc.tasks():
            values,deck=self.values(task);r=dc.measurements(values,task)
            self.assertTrue(r['passed']);self.assertEqual(len(r['stress']),20)
            self.assertIn('VA VDDIO 0 3.3\nVD VDDD 0 1.8',deck)
            self.assertIn('.temp 40',deck);self.assertIn('" ss\n',deck)
            self.assertEqual(deck.count('IB PB 0 35u'),1);self.assertNotIn('.tran',deck);self.assertNotIn('.dc',deck)
            self.assertIn('write bench.raw all',deck)

    def test_headroom_current_levels_reference_and_every_terminal_pair_are_checked(self):
        task=dc.tasks()[0];values,_=self.values(task)
        for failure in ('headroom','current','output','stress','reference'):
            bad=dict(values)
            if failure=='headroom':bad['v(xf.xref.t)']=.11
            if failure=='current':bad['i('+policy.op_parameters()['ref_tail_id']+')']=.0008
            if failure=='output':bad['v(ref_fast)']=1.8
            if failure=='stress':bad['v(xf.xref.o)']=2.01
            if failure=='reference':bad['v(xf.vcm)']=.92
            with self.subTest(failure=failure):self.assertFalse(dc.measurements(bad,task)['passed'])
        for failure in ('rail','missing','nonfinite','inconsistent'):
            bad=dict(values)
            if failure=='rail':bad['v(vddd)']=1.7
            if failure=='missing':del bad['i('+policy.op_parameters()['ref_tail_id']+')']
            if failure=='nonfinite':bad['v(ref)']=float('nan')
            if failure=='inconsistent':bad[policy.op_parameters()['ref_tail_id']]=.001
            with self.subTest(failure=failure),self.assertRaises(ValueError):dc.measurements(bad,task)

    def test_all_four_completed_standard_candidates_must_fail_before_artifacts(self):
        with tempfile.TemporaryDirectory() as d,patch.object(dc,'ROOT',Path(d)):
            root=Path(d);parent=root/'build/diagnostics/dll_slew_screen/s';parent.mkdir(parents=True)
            report=dict(ranked_survivors=[],candidates=[dict(variant=v,passed=False) for v in dc.screen.cal.CANDIDATES],
                        results=[dict(error=None) for t in dc.screen.tasks()])
            with patch.object(dc.screen,'verify',return_value=report),patch.object(dc.screen,'bound',return_value={'passed_gate':True}):
                self.assertEqual(dc.fallback_gate(parent),{'passed_gate':True})
            for failure in ('survivor','candidate','incomplete','numerical'):
                bad=deepcopy(report)
                if failure=='survivor':bad['ranked_survivors']=['nor4_inv4']
                if failure=='candidate':bad['candidates'][-1]['passed']=True
                if failure=='incomplete':bad['results'].pop()
                if failure=='numerical':bad['results'][0]['error']='numerical failure'
                with self.subTest(failure=failure),patch.object(dc.screen,'verify',return_value=bad),patch.object(dc.screen,'bound',return_value={}):
                    with self.assertRaises(ValueError):dc.fallback_gate(parent)
            with patch.object(dc,'engine',return_value='ngspice'),patch.object(dc,'fallback_gate',side_effect=ValueError('screen pending')), \
                 patch.object(policy,'circuit') as generate,self.assertRaises(ValueError):dc.prepare(parent)
            generate.assert_not_called();self.assertFalse((root/'build/diagnostics'/dc.NAMESPACE).exists())

    def test_all_static_points_required_and_partial_run_never_retries(self):
        tasks=dc.tasks();m=dict(tasks=tasks,identity={'scope':'DC only'})
        rows=[dict(task=t['id'],variant=t['variant'],result={'passed':True},error=None) for t in tasks]
        self.assertEqual(dc.aggregate(m,rows)['dc_ready_variants'],list(policy.VARIANTS))
        rows[0]['error']='incomplete';rows[0]['result']=None
        self.assertNotIn(rows[0]['variant'],dc.aggregate(m,rows)['dc_ready_variants'])
        for changed in (rows[:-1],rows+[rows[0]]):
            with self.assertRaises(ValueError):dc.aggregate(m,changed)
        bad=deepcopy(m);bad['tasks']=[]
        with self.assertRaises(ValueError):dc.aggregate(bad,[])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'manifest.json').write_text('{}');(root/'state.json').write_text('{}')
            with patch.object(dc,'bound',return_value={'tasks':[]}),patch.object(dc,'lease') as lease:
                with self.assertRaisesRegex(ValueError,'no retry'):dc.run(root)
                lease.assert_not_called()
