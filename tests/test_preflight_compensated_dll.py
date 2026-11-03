# SPDX-License-Identifier: GPL-3.0-only
import json
from contextlib import redirect_stdout, redirect_stderr
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import preflight_compensated_dll as flow
from spice_scope import closure_hash


class CompensatedDLLPreflight(unittest.TestCase):
    def test_cli_keeps_validator_progress_out_of_json_report(self):
        def check(*args):
            print('/cached/summary.json')
            return {'preflight_passed': True, 'qualified_phy': False}
        out, err = io.StringIO(), io.StringIO()
        with patch.object(flow, 'check', side_effect=check), redirect_stdout(out), redirect_stderr(err):
            flow.main(['pilot', 'reference', 'receiver', 'qualification'])
        self.assertTrue(json.loads(out.getvalue())['preflight_passed'])
        self.assertIn('/cached/summary.json', err.getvalue())

    def library(self):
        blocks = ['.subckt openlvds_driver_core D P N VR PB NB VA VD VS\nRDR P N 100\n.ends']
        for name in ['lvds_bias', 'openlvds_tx_core', 'openlvds_receiver_core', 'openlvds_ddr_rx']:
            ports = 'IREF NB VA VS' if name == 'lvds_bias' else 'A B'
            blocks.append(f'.subckt {name} {ports}\nR0 {ports.split()[0]} {ports.split()[1]} 10\n.ends')
        blocks.append('.subckt openlvds_dll CLK PH90 VSS\nRPH CLK PH90 10\n.ends')
        return '\n'.join(blocks)

    def deck(self):
        return '''IREF_TX IREF_TX 0 35u
IREF_RX IREF_RX 0 35u
XBT IREF_TX NBT VA 0 lvds_bias
XBR IREF_RX NBR VA 0 lvds_bias
XDT D P N VR IREF_TX NBT VA VD 0 openlvds_driver_core
.print tran V(P) V(N)
.end
'''

    def test_dll_overlay_preserves_new_driver_receiver_and_digital_circuits(self):
        base = self.library(); driver = base.replace('RDR P N 100', 'RDR P N 120')
        dll = base.replace('RPH CLK PH90 10', 'RPH CLK PH90 11')
        lib, report = flow.compose(base, driver, base, dll, self.deck())
        self.assertEqual(report['diagnostic_endpoint_bias_references'], 2)
        self.assertNotEqual(closure_hash(lib, 'openlvds_dll'), closure_hash(base, 'openlvds_dll'))
        self.assertEqual(closure_hash(lib, 'openlvds_driver_core'), closure_hash(driver, 'openlvds_driver_core'))
        for top in flow.PROTECTED:
            self.assertEqual(closure_hash(lib, top), closure_hash(driver, top))

    def test_wrong_dll_port_order_and_receiver_selection_are_rejected(self):
        base = self.library()
        for rx, dll in [(base, base.replace('CLK PH90 VSS', 'PH90 CLK VSS')),
                        (base.replace('R0 A B 10', 'R0 A B 11'), base)]:
            with self.assertRaises(ValueError):
                flow.compose(base, base, rx, dll, self.deck())

    def test_dll_dependency_cannot_trample_a_protected_digital_circuit(self):
        base = self.library()
        dll = base.replace('RPH CLK PH90 10', 'XBAD CLK PH90 openlvds_tx_core').replace('R0 A B 10', 'R0 A B 11')
        with self.assertRaisesRegex(ValueError, 'protected circuit'):
            flow.compose(base, base, base, dll, self.deck())

    def fixture(self, root):
        q = root / 'build/diagnostics/dll_qualification/test'; q.mkdir(parents=True)
        proof = root / 'source-proof'; proof.write_text('bound')
        (q / 'manifest.json').write_text(json.dumps({'identity': {'variant': flow.storage.VARIANT}}))
        a = dict(variant=flow.storage.VARIANT, manifest_sha256=flow.sha(q / 'manifest.json'),
                 producer_sha256=flow.sha(Path(flow.storage.__file__)), proofs={'source-proof': flow.sha(proof)})
        (q / 'storage_source_admission.json').write_text(json.dumps(a))
        (q / 'full.spice').write_text(self.library())
        return q

    def test_storage_profile_is_used_and_restored_without_executing_science(self):
        previous = flow.storage.native.CODE, flow.storage.native.slot
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); q = self.fixture(root)
            def validate(*args):
                self.assertIn('qualify_dll_storage.py', flow.storage.native.CODE)
            with patch.object(flow, 'ROOT', root), patch.object(flow.storage.native, 'validate', side_effect=validate), \
                    patch.object(flow.storage.native, 'execute') as execute:
                self.assertEqual(flow.dll_context(q), self.library())
                execute.assert_not_called()
        self.assertEqual((flow.storage.native.CODE, flow.storage.native.slot), previous)

    def test_changed_source_admission_rejects_before_native_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); q = self.fixture(root)
            (root / 'source-proof').write_text('changed')
            with patch.object(flow, 'ROOT', root), patch.object(flow.storage.native, 'validate') as validate:
                with self.assertRaisesRegex(ValueError, 'source admission changed'):
                    flow.dll_context(q)
                validate.assert_not_called()

    def test_profile_restores_globals_after_validation_failure(self):
        previous = flow.storage.native.CODE, flow.storage.native.slot
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); q = self.fixture(root)
            with patch.object(flow, 'ROOT', root), patch.object(flow.storage.native, 'validate', side_effect=ValueError('bad')):
                with self.assertRaisesRegex(ValueError, 'bad'):
                    flow.dll_context(q)
        self.assertEqual((flow.storage.native.CODE, flow.storage.native.slot), previous)


if __name__ == '__main__':
    unittest.main()
