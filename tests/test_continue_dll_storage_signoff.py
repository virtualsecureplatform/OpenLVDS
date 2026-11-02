# SPDX-License-Identifier: GPL-3.0-only
import json
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_dll_storage_signoff as signoff
import qualify_dll_storage as storage
import measure_dll_storage_stability as stability
import measure_dll_stability as measurement
import native_ac
import ota_operating_points as ota


class StorageSignoff(unittest.TestCase):
    def test_partial_and_completed_scopes_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            for phase in signoff.PHASES:
                signoff.fresh_scope(q, phase)
                scope = q/signoff.SCOPES[phase]; scope.mkdir()
                signoff.fresh_scope(q, phase)
                (scope/'partial.raw').write_bytes(b'retained numerical evidence')
                with self.assertRaisesRegex(ValueError, 'retained'):
                    signoff.fresh_scope(q, phase)
                self.assertEqual((scope/'partial.raw').read_bytes(), b'retained numerical evidence')
            with self.assertRaises(ValueError): signoff.fresh_scope(q, 'other')

    def test_all_actual_spice_producers_use_fair_leases_and_restore(self):
        old = storage.native.slot, measurement.slot, native_ac.slot, ota.slot, storage.native.CODE
        with patch('spice_dispatch.lease', return_value='lease') as lease, patch.object(storage, 'lease', lease), patch.object(stability, 'lease', lease):
            with self.assertRaisesRegex(RuntimeError, 'stop'):
                with signoff.resources():
                    for slot in [storage.native.slot, measurement.slot, native_ac.slot, ota.slot]:
                        self.assertEqual(slot(), 'lease')
                    self.assertIn('qualify_dll_storage.py', storage.native.CODE)
                    raise RuntimeError('stop')
            self.assertEqual(lease.call_count, 4)
            self.assertTrue(all(c.kwargs['priority'] == 1 for c in lease.call_args_list))
        self.assertEqual((storage.native.slot, measurement.slot, native_ac.slot, ota.slot, storage.native.CODE), old)

    def test_admission_requires_complete_exact_native_and_stability(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(signoff, 'ROOT', Path(tmp)), patch.object(signoff.full, 'full_native') as native, patch.object(signoff.full, 'all_pvt') as all_pvt:
            q = Path(tmp)/'build/diagnostics/dll_qualification/test'; q.mkdir(parents=True)
            (q/'manifest.json').write_text(json.dumps(dict(identity=dict(full_models=dict(inputs={'dll':'exact'})))))
            (q/'summary.json').write_text('{}')
            p = q/'stability_all_pvt/test/summary.json'; p.parent.mkdir(parents=True); p.write_text('{}')
            row = dict(native_full_passed=True, all_pvt_stability_passed=True, qualification=str(q.relative_to(tmp)),
                native_report_sha256=signoff.sha(q/'summary.json'), all_pvt_stability=str(p.relative_to(tmp)),
                all_pvt_stability_sha256=signoff.sha(p), full_inputs={'dll':'exact'})
            self.assertEqual(signoff.admission(q, row), p)
            native.assert_called_once_with(q); all_pvt.assert_called_once_with(q, p)
            for changes in [dict(native_full_passed=False), dict(all_pvt_stability_passed=False), dict(qualification='another'), dict(native_report_sha256='bad'), dict(all_pvt_stability_sha256='bad'), dict(full_inputs={'dll':'other'})]:
                with self.assertRaises(ValueError): signoff.admission(q, dict(row, **changes))
            native.side_effect=ValueError('native incomplete')
            with self.assertRaisesRegex(ValueError, 'native incomplete'): signoff.admission(q, row)

    def test_result_must_be_passing_and_owned_by_selected_phase(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(signoff, 'ROOT', Path(tmp)):
            q = Path(tmp)/'build/diagnostics/dll_qualification/test'
            p = q/'recovery/test/summary.json'; p.parent.mkdir(parents=True); p.write_text('{"passed":true}')
            inside = '/work/OpenLVDS/'+str(p.relative_to(tmp))
            self.assertEqual(signoff.result_path(q, 'recovery', inside), p)
            with self.assertRaises(ValueError): signoff.result_path(q, 'readiness', inside)
            p.write_text('{"passed":false}')
            with self.assertRaises(ValueError): signoff.result_path(q, 'recovery', inside)
            with self.assertRaises(ValueError): signoff.result_path(q, 'recovery', '/outside/summary.json')

    def test_prior_resource_context_cannot_dispatch_or_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(signoff, 'ROOT', Path(tmp)), patch.object(signoff.subprocess, 'run') as command:
            out = Path(tmp)/'build/diagnostics/dll_storage_signoff_followup/test'; out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(dict(identity=dict(files={}, max_workers=3, no_outer_lease=True))))
            (out/'state.json').write_text('retained')
            with self.assertRaisesRegex(ValueError, 'Prior signoff'): signoff.run(out)
            self.assertEqual((out/'state.json').read_text(), 'retained'); command.assert_not_called()

    def test_original_scientific_failure_stops_without_overwriting(self):
        import qualify_dll_recovery as engine
        with tempfile.TemporaryDirectory() as tmp, patch.object(signoff, 'ROOT', Path(tmp)), patch.object(signoff.full, 'full_native'), patch.object(signoff.full, 'all_pvt'), patch.object(signoff, 'resources', return_value=nullcontext()), patch.object(engine, 'run', return_value=1) as run:
            q = Path(tmp)/'build/diagnostics/dll_qualification/test'; q.mkdir(parents=True)
            (q/'manifest.json').write_text(json.dumps(dict(identity=dict(variant=signoff.full.VARIANT))))
            with self.assertRaisesRegex(ValueError, 'gate failed'):
                signoff.execute('recovery', q, q/'stability_all_pvt/test/summary.json')
            run.assert_called_once_with(q, q/'stability_all_pvt/test/summary.json', jobs=3)
            scope=q/'recovery/partial';scope.mkdir(parents=True)
            (scope/'bench.raw').write_bytes(b'failure evidence')
            run.reset_mock()
            with self.assertRaisesRegex(ValueError, 'retained'):
                signoff.execute('recovery', q, q/'stability_all_pvt/test/summary.json')
            run.assert_not_called()
            self.assertEqual((scope/'bench.raw').read_bytes(), b'failure evidence')

    def test_dead_prerequisite_cannot_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(signoff, 'ROOT', Path(tmp)), patch.object(signoff.full, 'owner', return_value=dict(MainPID='0', ActiveState='inactive', InvocationID='')):
            out = Path(tmp)/'build/diagnostics/dll_storage_signoff_followup/test'; out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(dict(identity=dict(files={}, max_workers=3, no_outer_lease=True,
                prerequisite='build/diagnostics/dll_storage_full_followup/test', unit='producer', owner=dict(MainPID='42', ActiveState='active', InvocationID='fixed')))))
            with self.assertRaisesRegex(ValueError, 'terminated'): signoff.run(out)
            self.assertEqual(json.loads((out/'state.json').read_text())['status'], 'held_for_diagnosis')
            self.assertFalse((out/'recovery.log').exists())


if __name__ == '__main__': unittest.main()
