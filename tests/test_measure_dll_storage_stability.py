# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import measure_dll_storage_stability as stability


class StorageStability(unittest.TestCase):
    def test_old_variant_is_rejected_without_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);q=root/'build/diagnostics/dll_qualification/old';q.mkdir(parents=True)
            (q/'manifest.json').write_text(json.dumps(dict(identity=dict(variant='ota_w8_c4'))))
            with patch.object(stability,'ROOT',root),patch.object(stability.storage.native,'execute') as execute:
                with self.assertRaisesRegex(ValueError,'corrected 16 pF'):
                    stability.admitted(q)
                execute.assert_not_called()

    def test_missing_native_operating_points_cannot_launch_simulations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);q=root/'build/diagnostics/dll_qualification/missing';q.mkdir(parents=True)
            m=dict(identity=dict(variant=stability.storage.VARIANT,screen='screen'),tasks=[])
            (q/'manifest.json').write_text(json.dumps(m))
            (q/'storage_source_admission.json').write_text(json.dumps(dict(variant=stability.storage.VARIANT,
                manifest_sha256=stability.sha(q/'manifest.json'),producer_sha256=stability.sha(Path(stability.storage.__file__)),proofs={})))
            with patch.object(stability,'ROOT',root),patch.object(stability.storage,'source_gate',return_value={}),patch.object(stability.storage.native,'execute') as execute:
                with self.assertRaisesRegex(ValueError,'Complete the native screen'):
                    stability.admitted(q)
                execute.assert_not_called()

    def test_ac_and_transient_resource_bindings_restore_on_failure(self):
        old=stability.measurement.slot,stability.native_ac.slot
        with self.assertRaises(RuntimeError):
            with stability.resources():
                self.assertIsNot(stability.measurement.slot,old[0])
                self.assertIsNot(stability.native_ac.slot,old[1])
                raise RuntimeError('injected')
        self.assertEqual((stability.measurement.slot,stability.native_ac.slot),old)

    def test_partial_measurements_are_preserved_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=Path(tmp);r=q/'stability_screen/partial';r.mkdir(parents=True)
            raw=r/'bench.raw';raw.write_bytes(b'original partial AC data')
            m=dict(identity=dict(full_models=dict(inputs={})))
            with patch.object(stability,'admitted',return_value=(m,[('ss',0),('tt',25),('ff',0)])),patch.object(stability,'context',return_value=(r,{})),patch.object(stability.measurement,'main') as launch:
                with self.assertRaisesRegex(ValueError,'Partial storage stability output retained'):
                    stability.run(q)
                launch.assert_not_called()
            self.assertEqual(raw.read_bytes(),b'original partial AC data')


if __name__=='__main__':
    unittest.main()
