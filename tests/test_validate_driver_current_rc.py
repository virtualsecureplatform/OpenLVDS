# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import validate_driver_current_rc as comparison


class CorrectedDriverRc(unittest.TestCase):
    def test_wire_rc_may_change_but_devices_and_ports_must_match(self):
        source='.subckt openlvds_driver_core P N\nX1 P N N N sky130_fd_pr__nfet_01v8 w=4 l=.15\nR1 P X 10\nC1 X N 1f\n.ends openlvds_driver_core\n'
        changed=source.replace('R1 P X 10','R1 P N 10').replace('C1 X N 1f','C1 P N 1f')
        self.assertEqual(comparison.device_signature(source),comparison.device_signature(changed))
        self.assertNotEqual(comparison.device_signature(source),comparison.device_signature(changed.replace('w=4','w=8')))
        self.assertNotEqual(comparison.device_signature(source),comparison.device_signature(changed.replace('core P N','core N P')))

    def test_partial_or_unattested_trace_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);raw=folder/'bench.raw';raw.write_bytes(b'original partial')
            with patch.object(comparison.rc_trace,'verified',return_value=None),patch.object(comparison,'engine',return_value='ngspice'):
                with self.assertRaisesRegex(ValueError,'do not overwrite or restart'):
                    comparison.guard_trace(folder,'scope',{},'runtime')
            self.assertEqual(raw.read_bytes(),b'original partial')

    def test_attested_trace_for_another_driver_cannot_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'trace_evidence.json').write_text('{}')
            evidence=dict(scope_sha256='other',inputs={'driver':'other'})
            with patch.object(comparison.rc_trace,'verified',return_value=evidence),patch.object(comparison,'engine',return_value='ngspice'):
                with self.assertRaisesRegex(ValueError,'do not overwrite or restart'):
                    comparison.guard_trace(folder,'selected',{'driver':'selected'},'runtime')

    def test_profile_restores_after_failure_and_uses_exact_declared_views(self):
        old=comparison.validation.library,comparison.validation.slot
        views=dict(full=(b'full',{'driver':'full'}),fast=(b'fast',{'driver':'fast'}))
        with self.assertRaises(RuntimeError):
            with comparison.profile(views):
                self.assertEqual(comparison.validation.library(fast=False),(b'full',{'driver':'full'},{}))
                self.assertEqual(comparison.validation.library(fast=True),(b'fast',{'driver':'fast'},{}))
                raise RuntimeError('injected')
        self.assertEqual((comparison.validation.library,comparison.validation.slot),old)


if __name__=='__main__':
    unittest.main()
