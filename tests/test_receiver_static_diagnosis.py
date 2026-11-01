# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import json
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from receiver_static_diagnosis import remove_clamps, capture_manifest, digest
from receiver_fast_restore_experiment import source_variant
from dll_campaign import text_block
from spice_library import replace


class ReceiverStaticDiagnosis(unittest.TestCase):
    def test_repreparation_preserves_original_bytes_despite_key_order(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'manifest.json'
            capture_manifest(path, dict(identity=dict(code=dict(z='last', a='first')), qualified_phy=False))
            before = path.read_bytes()
            stamp = digest(path)
            capture_manifest(path, dict(qualified_phy=False, identity=dict(code=dict(a='first', z='last'))))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(digest(path), stamp)

    def test_changed_manifest_content_or_json_type_cannot_replace_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'manifest.json'
            path.write_text(json.dumps(dict(qualified_phy=False)))
            before = path.read_bytes()
            for value in [dict(qualified_phy=True), dict(qualified_phy=0)]:
                with self.assertRaisesRegex(ValueError, 'manifest changed'):
                    capture_manifest(path, value)
                self.assertEqual(path.read_bytes(), before)

    def test_only_the_two_clamp_rows_are_removed(self):
        source = source_variant((Path(__file__).resolve().parents[1] / 'analog/openlvds.spice').read_text())
        result = remove_clamps(source)
        old = text_block(source, 'openlvds_receiver_core')
        expected = '\n'.join(line for line in old.split('\n') if not line.startswith(('XCLAMP0 ', 'XCLAMP1 ')))
        self.assertEqual(result, replace(source, 'openlvds_receiver_core', expected))
        self.assertIn('XTRACK CO_TRACK CO_TRACK', result)
        self.assertIn('XIB0 CO RESTORE0 VDDD VSS lvds_rx_restore_mid', result)

    def test_unexpected_reference_or_missing_clamp_is_rejected(self):
        source = source_variant((Path(__file__).resolve().parents[1] / 'analog/openlvds.spice').read_text())
        for changed in [source.replace('XCLAMP0 CO VREF', 'XCLAMP0 CO CO_TRACK'),
                        source.replace('XCLAMP0 CO VREF', 'XCLAMP9 CO VREF')]:
            with self.assertRaisesRegex(ValueError, 'Unexpected CO clamp'):
                remove_clamps(changed)


if __name__ == '__main__':
    unittest.main()
