# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import validate_dll_storage_rc as comparison


class StorageDllRc(unittest.TestCase):
    def test_incomplete_native_screen_cannot_dispatch_missing_prerequisites(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(comparison,'ROOT',Path(tmp)):
            out=Path(tmp)/'build/diagnostics/dll_qualification/test';out.mkdir(parents=True)
            names=[f'phase_{p}_{t}_{offset}ps' for p,t in [('ss',0),('tt',25),('ff',0)]
                for offset in [0,50,-50,150,-150,300,-300]]+['loop_ss_0','loop_tt_25','loop_ff_0']
            (out/'manifest.json').write_text(json.dumps(dict(tasks=[dict(id=n) for n in names])))
            (out/'screen_summary.json').write_text('{"passed":true}')
            for n in names[:-1]:
                (out/n).mkdir();(out/n/'summary.json').write_text('{}')
            with patch.object(comparison.admission,'admitted') as admit:
                with self.assertRaisesRegex(ValueError,'Complete all twenty-four'):
                    comparison.screen_gate(out)
                admit.assert_not_called()

    def test_other_namespace_cannot_request_cached_native_measurements(self):
        with patch.object(comparison.admission,'admitted') as admit:
            with self.assertRaisesRegex(ValueError,'isolated DLL'):
                comparison.screen_gate(Path('/tmp/elsewhere'))
            admit.assert_not_called()

    def views(self,root):
        text=('.subckt lvds_bias B G\nRBIAS B G 100\n.ends lvds_bias\n'
              '.subckt openlvds_dll_analog A B G\n'
              'XM A B G G sky130_fd_pr__nfet_01v8 w=8 l=.15\n'
              'RWIRE A B 2\nCWIRE A G 1f\n.ends openlvds_dll_analog\n')
        for mode in ['full','fast']:(root/(mode+'.spice')).write_text(text)
        inputs=dict(openlvds_dll_analog='native',lvds_pfd='pfd',lvds_bias='bias')
        return dict(full_models=dict(inputs=dict(inputs)),fast_models=dict(inputs=dict(inputs)))

    def test_wire_reduction_keeps_bias_and_every_non_wire_statement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);identity=self.views(root);fast=root/'fast.spice'
            fast.write_text(fast.read_text().replace('RWIRE A B 2','RWIRE A B 1').replace('CWIRE A G 1f','CWIRE B G 1f'))
            with patch.object(comparison,'ProbeNetwork') as probes:
                result=comparison.checked_views(root,identity)
                self.assertEqual(set(result),{'full','fast'})
                self.assertEqual(probes.return_value.validate.call_count,2)

    def test_bias_or_mos_changes_cannot_be_admitted_as_rc_approximations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);identity=self.views(root);fast=root/'fast.spice';source=fast.read_text()
            for text,message in [(source.replace('RBIAS B G 100','RBIAS B G 200'),'exact shared bias'),
                                 (source.replace('w=8','w=16'),'non-wire device')]:
                fast.write_text(text)
                with self.assertRaisesRegex(ValueError,message):
                    comparison.checked_views(root,identity)

    def test_missing_or_extra_model_inputs_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);identity=self.views(root)
            identity['fast_models']['inputs'].pop('lvds_pfd')
            with self.assertRaisesRegex(ValueError,'three model inputs'):
                comparison.checked_views(root,identity)

    def test_profile_restores_on_failure_and_maps_only_declared_views(self):
        old=comparison.validation.library,comparison.validation.slot
        views=dict(full=(b'full',{'dll':'native'}),fast=(b'fast',{'dll':'approximate'}))
        with self.assertRaises(RuntimeError):
            with comparison.profile(views):
                self.assertEqual(comparison.validation.library(fast=False),(b'full',{'dll':'native'},{}))
                self.assertEqual(comparison.validation.library(fast=True),(b'fast',{'dll':'approximate'},{}))
                raise RuntimeError('injected')
        self.assertEqual((comparison.validation.library,comparison.validation.slot),old)


if __name__=='__main__':
    unittest.main()
