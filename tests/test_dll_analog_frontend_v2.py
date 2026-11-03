import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dll_analog_frontend_v2 as policy
import probe_dll_analog_frontend_dc_v2 as revised


class AlwaysBiasedFrontend(unittest.TestCase):
    def values(self,task):
        model=policy.circuit(task['variant'])[0]
        native='.subckt lvds_bias PB NB VDDIO VSS\nR0 PB NB 1k\nR1 NB VSS 1k\n.ends lvds_bias\n'
        with revised.profile():deck,nodes=revised.dc.fixture(task,Path('/fixture'),Path('/pdk/sky130.lib.spice'),native+model)
        result={'v('+n.replace(':','.').lower()+')':0. for n in nodes}
        def v(n,value):result['v('+n.replace(':','.').lower()+')']=value
        for n,value in [('VDDD',1.8),('VDDIO',3.3),('PB',1.2),('XF:NTAIL',.65),('XF:PTAIL',.6),('XF:VCM',.9),('REF',task['ref_v']),('FDB',task['fb_v'])]:v(n,value)
        for side,signal,out in [('XREF',task['ref_v'],'REF_FAST'),('XFB',task['fb_v'],'FDB_FAST')]:
            prefix='XF:'+side+':'
            for n,value in [('L',.8 if signal==0 else .4),('R',.4 if signal==0 else .8),('DL',.2 if signal==0 else .1),('DR',.1 if signal==0 else .2),
                            ('T',.15),('TP',1.3),('QL',.6),('QO',.1 if signal==0 else 1.3),('MID',1.8 if signal==0 else 0)]:v(prefix+n,value)
            v(out,0 if signal==0 else 1.8)
        target=policy.VARIANTS[task['variant']]['tail_ua']*1e-6
        for name,vector in policy.op_parameters().items():
            field=name.rsplit('_',1)[-1];p=name.startswith(('p_reference','ref_dec','fb_dec'))
            key='i('+vector+')' if field=='id' else 'v('+vector+')' if field=='vdsat' else vector
            result[key]={'id':-target if p else target,'gm':.001,'gds':.000001,'vdsat':-.08 if p else .05}[field]
        result.update({'i(va)':-.0005,'i(vd)':-.0012})
        return result,deck

    def test_matched_resistor_preamp_and_pmos_stage_keep_distinct_biases(self):
        self.assertEqual(len(policy.VARIANTS),4);self.assertEqual(len(policy.tail_roles()),4);self.assertEqual(len(policy.op_parameters()),24)
        for variant,spec in policy.VARIANTS.items():
            model,devices=policy.circuit(variant)
            self.assertEqual(len(devices),28);self.assertEqual(len({d['name'] for d in devices}),28)
            self.assertIn('XLOAD_L_0 VDDD L VSS',model);self.assertIn('XLOAD_R_0 VDDD R VSS',model)
            self.assertIn('XDIV_L_0_3 DL VSS VSS',model);self.assertIn('XDIV_R_0_3 DR VSS VSS',model)
            self.assertEqual('XLOAD_L_1' in model,spec['tail_ua']==280)
            self.assertIn('XDEC0 QL DR TP VDDD '+policy.P,model)
            self.assertIn('XDEC1 QO DL TP VDDD '+policy.P,model)
            self.assertIn('XTAIL T NTAIL VSS VSS '+policy.N+' w=200 l=0.3',model)
            self.assertIn('XTAIL2 TP PTAIL VDDD VDDD '+policy.P+' w=400 l=0.3',model)
            self.assertNotIn('\nI',model);self.assertNotIn('lvds_bias',model)
        with self.assertRaises(ValueError):policy.circuit('unbounded')

    def test_all_twenty_static_points_measure_all_four_tails_and_pmos_sign(self):
        with revised.profile():tasks=revised.dc.tasks()
        for task in tasks:
            values,deck=self.values(task);r=revised.measurements(values,task)
            self.assertTrue(r['passed']);self.assertEqual(len(r['tails']),4);self.assertEqual(len(r['stress']),28)
            self.assertLess(r['references']['p_reference']['id'],0)
            self.assertGreater(r['tails']['ref_dec']['headroom_v'],.02)
            self.assertIn('VA VDDIO 0 3.3\nVD VDDD 0 1.8',deck);self.assertEqual(deck.count('IB PB 0 35u'),1)

    def test_each_stage_current_headroom_and_all_terminal_stresses_remain_gates(self):
        task=dict(id='unit',variant='tail140_w20',ref_v=0,fb_v=0);values,_=self.values(task)
        for failure in ('pre_headroom','decision_headroom','decision_current','stress','common','level'):
            bad=dict(values)
            if failure=='pre_headroom':bad['v(xf.xref.t)']=.06
            if failure=='decision_headroom':bad['v(xf.xref.tp)']=1.75
            if failure=='decision_current':bad['i('+policy.op_parameters()['ref_dec_id']+')']=-.0005
            if failure=='stress':bad['v(xf.xref.qo)']=2.1
            if failure=='common':bad['v(xf.vcm)']=.92
            if failure=='level':bad['v(ref_fast)']=1.8
            with self.subTest(failure=failure):self.assertFalse(revised.measurements(bad,task)['passed'])
        for failure in ('missing','nonfinite','rail'):
            bad=dict(values)
            if failure=='missing':del bad['i('+policy.op_parameters()['ref_dec_id']+')']
            if failure=='nonfinite':bad['v(ref)']=float('nan')
            if failure=='rail':bad['v(vddd)']=1.7
            with self.subTest(failure=failure),self.assertRaises(ValueError):revised.measurements(bad,task)

    def test_profile_restores_original_producer_even_on_failure(self):
        old=revised.dc.policy,revised.dc.NAMESPACE,revised.dc.measurements
        with self.assertRaises(RuntimeError):
            with revised.profile():
                self.assertIs(revised.dc.policy,policy);self.assertEqual(revised.dc.NAMESPACE,revised.NAMESPACE)
                raise RuntimeError('profile exit')
        self.assertEqual((revised.dc.policy,revised.dc.NAMESPACE,revised.dc.measurements),old)

    def test_prepare_and_bound_capture_new_revision_without_mutating_original(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);oldroot=revised.ROOT
            for name in ('probe_dll_analog_frontend_dc_v2.py','dll_analog_frontend_v2.py'):
                p=root/'scripts'/name;p.parent.mkdir(exist_ok=True);shutil.copyfile(oldroot/'scripts'/name,p)
            q=root/'q';q.mkdir();native='.subckt lvds_bias PB NB VDDIO VSS\nR0 PB NB 1k\nR1 NB VSS 1k\n.ends lvds_bias\n';(q/'full.spice').write_text(native)
            pdk=root/'pdk.spice';pdk.write_text('pinned PDK fixture')
            failed=root/'failed';failed.mkdir()
            for n in ('manifest.json','summary.json'):(failed/n).write_text('{}')
            old=dict(identity=dict(parent='build/diagnostics/dll_slew_screen/s',qualification_reference='q',
                                  pdk=dict(path=str(pdk),sha256=revised.sha(pdk)),code={},inputs={'q/full.spice':revised.sha(q/'full.spice')}),tasks=[],libraries={})
            with patch.object(revised,'ROOT',root),patch.object(revised.dc,'ROOT',root),patch.object(revised,'failed_context',return_value=old), \
                 patch.object(revised.dc,'fallback_gate',return_value={}),patch.object(revised,'engine',return_value='ngspice'):
                out=revised.prepare(failed);m=revised.bound(out)
                self.assertEqual(m['identity']['policy'],policy.VERSION);self.assertEqual(m['identity']['failed_revision'],'failed')
                self.assertEqual(len(m['tasks']),20);self.assertIn('dll_analog_frontend_v2.py',m['identity']['code'])
                self.assertFalse(m['qualified_phy']);self.assertEqual((failed/'summary.json').read_text(),'{}')
                deck=out/m['tasks'][0]['id']/'bench.cir';deck.write_text(deck.read_text().replace('VD VDDD 0 1.8','VD VDDD 0 1.7'))
                with self.assertRaises(ValueError):revised.bound(out)

    def test_failed_original_gate_is_required_before_any_new_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(revised,'engine',return_value='ngspice'),patch.object(revised,'failed_context',side_effect=ValueError('original pending')),self.assertRaises(ValueError):revised.prepare(root/'pending')
            self.assertEqual(list(root.iterdir()),[])
