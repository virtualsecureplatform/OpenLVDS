from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dll_analog_frontend_v2_tailtrim as policy
import probe_dll_analog_frontend_dc_tailtrim as revised
import test_dll_analog_frontend_v2_fingered as fixtures


class PreampTailCorrection(unittest.TestCase):
    def test_only_preamp_tail_ratio_changes_with_legal_actual_fingers(self):
        for variant in policy.VARIANTS:
            text,devices=policy.circuit(variant);_,before=policy.base.circuit(variant)
            self.assertEqual(len(devices),125);self.assertEqual(len({d['name'] for d in devices}),125)
            self.assertIn('.subckt '+policy.PAIR+' '+' '.join(policy.PORTS),text)
            self.assertIn('XTAIL_F11 ',text);self.assertNotIn('XTAIL_F12 ',text)
            self.assertEqual(policy.groups()['n_reference']['fingers'],10)
            self.assertEqual(policy.groups()['ref_pre']['fingers'],12)
            self.assertEqual(policy.groups()['fb_pre']['fingers'],12)
            self.assertEqual(policy.groups()['ref_dec']['fingers'],20)
            self.assertAlmostEqual(sum(d['width_um']*d['length_um'] for d in devices)-sum(d['width_um']*d['length_um'] for d in before),24)
        self.assertEqual(len(policy.op_parameters()),376)

    def test_same_measurement_limits_consume_all_twelve_preamp_fingers(self):
        task=dict(variant='tail140_w20',ref_v=0,fb_v=0);values,_=fixtures.LegalParallelFrontend().values(task)
        for group in ('ref_pre','fb_pre'):
            for i in range(12):
                for field in ('id','gm','gds','vdsat'):
                    vector=policy.op_parameters()[group+'_f'+str(i)+'_'+field]
                    key='i('+vector+')' if field=='id' else 'v('+vector+')' if field=='vdsat' else vector
                    values[key]={'id':140e-6/12,'gm':.001/12,'gds':.000001/12,'vdsat':.05}[field]
        with patch.object(revised.original,'policy',policy):
            report=revised.original.measurements(values,task)
            self.assertTrue(report['passed']);self.assertEqual(report['parallel_device_observations']['ref_pre']['finger_count'],12)
            self.assertEqual(len(report['stress']),125)
            bad=dict(values);bad['v(xf.xref.t)']=.06
            self.assertFalse(revised.original.measurements(bad,task)['passed'])

    def test_correction_requires_complete_current_limited_parent_not_other_failures(self):
        q=dict(parallel_devices_passed=True,common_mode_passed=True,reference_matching_passed=True,
               references={'n_reference':{'passed':True},'p_reference':{'passed':True}},stress=[{'passed':True}],
               outputs={'ref':{'passed':True},'fb':{'passed':True}},
               tails={'ref_pre':{'headroom_v':.06,'passed':False},'fb_pre':{'headroom_v':.06,'passed':False},'ref_dec':{'passed':True},'fb_dec':{'passed':True}})
        report=dict(dc_ready_variants=[],results=[dict(result=q)])
        with tempfile.TemporaryDirectory() as d,patch.object(revised,'ROOT',Path(d)):
            parent=Path(d)/'build/diagnostics'/revised.PARENT_NAMESPACE/'p';parent.mkdir(parents=True)
            with patch.object(revised.original,'verify',return_value=report),patch.object(revised.original,'bound',return_value={'parent':'same'}):
                self.assertEqual(revised.parent_context(parent),{'parent':'same'})
            for failure in ('headroom','decision','stress','levels','reference','survivor'):
                bad=deepcopy(report);r=bad['results'][0]['result']
                if failure=='headroom':r['tails']['ref_pre']['headroom_v']=.01
                if failure=='decision':r['tails']['ref_dec']['passed']=False
                if failure=='stress':r['stress'][0]['passed']=False
                if failure=='levels':r['outputs']['ref']['passed']=False
                if failure=='reference':r['reference_matching_passed']=False
                if failure=='survivor':bad['dc_ready_variants']=['tail140_w20']
                with self.subTest(failure=failure),patch.object(revised.original,'verify',return_value=bad),patch.object(revised.original,'bound',return_value={}):
                    with self.assertRaises(ValueError):revised.parent_context(parent)

    def test_profile_records_correction_and_restores_ancestors(self):
        original=revised.original;previous=original.policy,original.NAMESPACE,original.original.failed_context
        old={'identity':{'inputs':{},'code':{}}}
        with patch.object(original.original,'failed_context',return_value=old):
            with revised.profile({'parent/raw':'captured'}):
                m=original.original.failed_context(Path('old'))
                self.assertEqual(m['identity']['inputs'],{'parent/raw':'captured'})
                self.assertIn('dll_analog_frontend_v2_tailtrim.py',m['identity']['code'])
                self.assertIs(original.policy,policy)
                self.assertEqual(old,{'identity':{'inputs':{},'code':{}}})
        self.assertEqual((original.policy,original.NAMESPACE,original.original.failed_context),previous)

    def test_parent_manifest_must_be_unique_and_failed_gate_creates_nothing(self):
        with tempfile.TemporaryDirectory() as d,patch.object(revised,'ROOT',Path(d)):
            root=Path(d);out=root/'build/diagnostics'/revised.NAMESPACE/'new';out.mkdir(parents=True)
            name='build/diagnostics/'+revised.PARENT_NAMESPACE+'/parent/manifest.json'
            (out/'manifest.json').write_text(json.dumps({'identity':{'inputs':{name:'hash'}}}))
            self.assertEqual(revised.parent_from_inputs(out),root/Path(name).parent)
            (out/'manifest.json').write_text(json.dumps({'identity':{'inputs':{}}}))
            with self.assertRaises(ValueError):revised.parent_from_inputs(out)
        with tempfile.TemporaryDirectory() as d,patch.object(revised,'parent_context',side_effect=ValueError('not current limited')):
            root=Path(d)
            with self.assertRaises(ValueError):revised.prepare(root/'parent',root/'invalid')
            self.assertEqual(list(root.iterdir()),[])
