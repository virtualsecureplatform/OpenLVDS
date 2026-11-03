from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dll_analog_frontend_v2_fingered as policy
import probe_dll_analog_frontend_dc_v2_fingered as revised
import test_dll_analog_frontend_v2 as fixtures


class LegalParallelFrontend(unittest.TestCase):
    def values(self,task):
        original=fixtures.AlwaysBiasedFrontend().values(dict(task,id='unit'))[0];values=dict(original)
        logical=policy.original.op_parameters();vectors=policy.op_parameters()
        for group,role in policy.groups().items():
            for field in ('id','gm','gds','vdsat'):
                old=logical[group+'_'+field];key='i('+old+')' if field=='id' else 'v('+old+')' if field=='vdsat' else old
                value=values.pop(key)
                for i in range(role['fingers']):
                    vector=vectors[group+'_f'+str(i)+'_'+field]
                    name='i('+vector+')' if field=='id' else 'v('+vector+')' if field=='vdsat' else vector
                    values[name]=value/role['fingers'] if field!='vdsat' else value
        return values,original

    def test_explicit_legal_fingers_preserve_total_geometry_and_private_interface(self):
        for variant in policy.VARIANTS:
            text,devices=policy.circuit(variant);_,before=policy.original.circuit(variant)
            self.assertEqual(len(devices),121);self.assertEqual(len({d['name'] for d in devices}),121)
            self.assertNotIn('w=200',text);self.assertNotIn('w=400',text)
            self.assertIn('.subckt '+policy.PAIR+' '+' '.join(policy.PORTS),text)
            self.assertAlmostEqual(sum(d['width_um']*d['length_um'] for d in devices),sum(d['width_um']*d['length_um'] for d in before))
            self.assertTrue(all(d['width_um']<=40 for d in devices))
        self.assertEqual(len(policy.op_parameters()),360);self.assertEqual(len(set(policy.op_parameters().values())),360)

    def test_every_actual_finger_is_measured_and_effective_currents_sum(self):
        for variant in policy.VARIANTS:
            for ref,fb in ((0,0),(.9,.9),(1.8,1.8),(0,1.8),(1.8,0)):
                task=dict(variant=variant,ref_v=ref,fb_v=fb);values,old=self.values(task)
                report=revised.measurements(values,task)
                self.assertTrue(report['passed']);self.assertEqual(len(report['stress']),121)
                self.assertEqual(sum(g['finger_count'] for g in report['parallel_device_observations'].values()),90)
                self.assertAlmostEqual(report['tails']['ref_pre']['drain_current_magnitude_a'],policy.VARIANTS[variant]['tail_ua']*1e-6)
                self.assertAlmostEqual(report['tails']['ref_dec']['drain_current_magnitude_a'],policy.VARIANTS[variant]['tail_ua']*1e-6)

    def test_missing_opposite_or_nonuniform_finger_cannot_hide_in_effective_sum(self):
        task=dict(variant='tail140_w20',ref_v=0,fb_v=0);values,_=self.values(task)
        for failure in ('nonuniform','opposite','missing'):
            bad=dict(values)
            if failure=='nonuniform':bad['i('+policy.op_parameters()['ref_pre_f0_id']+')']*=2
            if failure=='opposite':bad['i('+policy.op_parameters()['ref_dec_f0_id']+')']*=-1
            if failure=='missing':del bad['v('+policy.op_parameters()['ref_dec_f0_vdsat']+')']
            with self.subTest(failure=failure):
                if failure=='missing':
                    with self.assertRaises(ValueError):revised.measurements(bad,task)
                else:
                    report=revised.measurements(bad,task);self.assertFalse(report['passed']);self.assertFalse(report['parallel_devices_passed'])

    def test_profile_stamps_new_producers_without_mutating_failure_receipt(self):
        module=revised.original;previous=module.policy,module.NAMESPACE,module.measurements,module.failed_context
        old={'identity':{'inputs':{},'code':{}}}
        with patch.object(module,'failed_context',return_value=old):
            with revised.profile({'invalid-model.log':'captured'}):
                admitted=module.failed_context(Path('original'))
                self.assertIn('dll_analog_frontend_v2_fingered.py',admitted['identity']['code'])
                self.assertEqual(admitted['identity']['inputs'],{'invalid-model.log':'captured'})
                self.assertEqual(old,{'identity':{'inputs':{},'code':{}}})
                self.assertIs(module.policy,policy)
        self.assertEqual((module.policy,module.NAMESPACE,module.measurements,module.failed_context),previous)

    def test_invalid_model_prerequisite_refuses_unrelated_numerical_failure(self):
        with tempfile.TemporaryDirectory() as d,patch.object(revised,'ROOT',Path(d)),patch.object(revised.original,'bound'):
            root=Path(d);out=root/'build/diagnostics'/revised.original.NAMESPACE/'invalid';case=out/'case';case.mkdir(parents=True)
            (case/'summary.json').write_text('{"error":"model failure"}');(case/'ngspice.log').write_text('could not find a valid modelname')
            self.assertIn(str((case/'ngspice.log').relative_to(root)),revised.invalid_context(out))
            (case/'ngspice.log').write_text('unrelated failure')
            with self.assertRaises(ValueError):revised.invalid_context(out)
