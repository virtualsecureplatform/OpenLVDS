# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import capture_native_live_tail_v290 as p

class LiveTailTests(unittest.TestCase):
    def fixture(self,path,rows,extra=b''):
        header=b'Title: incomplete fixture\nFlags: real\nNo. Variables: 3\nNo. Points: 0\nVariables:\n0 time time\n1 v(in) voltage\n2 v(out) voltage\nBinary:\n'
        path.write_bytes(header+b''.join(struct.pack('<ddd',*row) for row in rows)+extra);return header

    def test_partial_final_frame_is_excluded_and_exact_tail_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bench.raw';rows=[(k*1e-12,.0,k*.01) for k in range(10)];h=self.fixture(path,rows,b'partial')
            header,window,r=p.tail(path,4)
            self.assertEqual(header,h);self.assertEqual(window,b''.join(struct.pack('<ddd',*row) for row in rows[-4:]))
            self.assertEqual((r['complete_frames_observed'],r['copied_frames'],r['first_copied_frame'],r['ignored_partial_frame_bytes']),(10,4,6,7))
            self.assertAlmostEqual(r['median_window_step_ps'],1);self.assertFalse(r['source_waveform_complete']);self.assertFalse(r['qualified_phy'])
            self.assertAlmostEqual(r['largest_voltage_ranges'][0]['peak_to_peak_v'],.03)

    def test_nonfinite_nonmonotonic_missing_header_and_unbounded_reads_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bench.raw'
            for rows in [[(0,0,0),(0,0,1)],[(0,0,0),(1e-12,float('nan'),1)],[(0,0,0)]]:
                self.fixture(path,rows)
                with self.assertRaises(ValueError):p.tail(path)
            path.write_bytes(b'not binary')
            with self.assertRaises(ValueError):p.tail(path)
            with self.assertRaises(ValueError):p.tail(path,1025)

    def test_current_python_process_cannot_be_mistaken_for_solver(self):
        with self.assertRaisesRegex(ValueError,'live native ngspice'):p.process(os.getpid())

if __name__=='__main__':unittest.main()
