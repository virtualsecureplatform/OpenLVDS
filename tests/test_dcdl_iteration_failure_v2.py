# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_dcdl_iterations_v2 as diagnosis


class IterationFailureDiagnosisTests(unittest.TestCase):
    def raw(self,date=b'first'):
        header=b'Date: '+date+b'\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 2\nNo. Points: 0\nVariables:\n0 time time\n1 v(in) voltage\nBinary:\n'
        return header+struct.pack('=6d',0.,0.,1e-10,0.,6.544043994140895e-10,0.)

    def test_aborted_prefix_remains_unqualified_and_payload_ignores_header_date(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'bench.raw';p.write_bytes(self.raw());a=diagnosis.prefix(p)
            p.write_bytes(self.raw(b'second'));b=diagnosis.prefix(p)
            self.assertEqual(a,b);self.assertEqual(a['complete_records'],3)
            self.assertFalse(a['completed_transient']);self.assertFalse(a['qualified_phy'])

    def test_truncated_and_invalid_binary_prefixes_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'bench.raw'
            for data in [self.raw()[:-1],self.raw().replace(b'Flags: real',b'Flags: complex'),
                         self.raw().split(b'Binary:')[0],self.raw()[:-8]+struct.pack('=d',0.)[:-1]]:
                p.write_bytes(data)
                with self.assertRaises(ValueError):diagnosis.prefix(p)

    def test_failure_requires_explicit_terminal_abort_and_reports_node_without_root_cause(self):
        log='Timestep too small; time = 6.54404e-10, timestep = 2.5e-24: trouble with node "bin#branch"\nrun simulation(s) aborted\nTotal elapsed time (seconds) = 5649.450\n'
        result=diagnosis.failure(log)
        self.assertEqual(result['reported_node'],'bin#branch')
        self.assertEqual(result['reported_time_s'],6.54404e-10)
        for invalid in [log.replace('run simulation(s) aborted',''),log+log,log.replace('2.5e-24','-2.5e-24')]:
            with self.assertRaises(ValueError):diagnosis.failure(invalid)
