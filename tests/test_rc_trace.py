# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from spice_scope import closure_hash
import rc_trace


class TraceEvidence(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.out=Path(folder.name)
        self.lib=b'.subckt DUT A Y\nR1 A Y 10\n.ends DUT\n'
        self.deck='reference deck';self.inputs={'device':'network hash'}
        for name,data in [('library.spice',self.lib),('bench.cir',self.deck.encode()),
                ('bench.cir.prn',b'completed waveform'),('producer.py',b'original producer')]:
            (self.out/name).write_bytes(data)
        self.scope=closure_hash(self.lib,'DUT')

    def record(self):
        return rc_trace.record(self.out,'DUT',self.scope,self.inputs,'fixture','engine v1','requirements v1')

    def matches(self,provenance='engine v1'):
        return rc_trace.matching(self.out,self.deck,self.scope,self.inputs,'fixture',provenance,'requirements v1')

    def test_unattested_legacy_waveform_cannot_be_reused(self):
        self.assertFalse(self.matches())

    def test_current_reference_reuses_but_changed_simulator_does_not(self):
        self.record();self.assertTrue(self.matches())
        self.assertFalse(self.matches('engine v2'))

    def test_changed_waveform_and_producer_are_rejected(self):
        self.record();(self.out/'bench.cir.prn').write_bytes(b'changed waveform')
        self.assertFalse(self.matches())
        (self.out/'bench.cir.prn').write_bytes(b'completed waveform')
        (self.out/'producer.py').write_bytes(b'replaced producer')
        self.assertFalse(self.matches())

    def test_changed_fixture_is_rejected(self):
        self.record()
        self.assertFalse(rc_trace.matching(self.out,'other deck',self.scope,self.inputs,'fixture','engine v1','requirements v1'))

    def test_certificate_cannot_point_at_rewritten_metadata(self):
        self.record();path=self.out/'trace_evidence.json';original=rc_trace.digest(path.read_bytes())
        path.write_bytes(path.read_bytes()+b'\n')
        self.assertIsNone(rc_trace.verified(self.out,'fixture','engine v1','requirements v1',original))


if __name__=='__main__':unittest.main()
