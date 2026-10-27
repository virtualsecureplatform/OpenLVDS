# SPDX-License-Identifier: GPL-3.0-only
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dll_case import case_name,trace_duty


class DLLClockEvidence(unittest.TestCase):
    def test_duty_specific_evidence_cannot_alias_nominal(self):
        self.assertEqual(case_name('tt',25), 'dll_tt_25')
        self.assertEqual(case_name('tt',25,380), 'dll_tt_25_380m')
        self.assertNotEqual(case_name('tt',25,400,.45),case_name('tt',25))
        self.assertEqual(case_name('tt',25,400,.5181234),case_name('tt',25,400,.518123))

    def test_trace_excludes_incomplete_boundary_cycles(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'clock.csv'
            path.write_text('time_ns,level\n0,0\n1,1\n2.2,0\n3,1\n4.2,0\n5,1\n5.1,0\n')
            self.assertEqual(trace_duty(path),.6)
            path.write_text('time_ns,level\n0,0\n1,1\n')
            with self.assertRaises(ValueError):trace_duty(path)


if __name__=='__main__':unittest.main()
