# SPDX-License-Identifier: GPL-3.0-only
"""Guard all-vector prefix preservation and rejection of incomplete observations."""
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import capture_quiet_reference_v357 as p


class QuietReferenceTests(unittest.TestCase):
    header=b'Title: native quiet\nFlags: real\nNo. Variables: 3\nNo. Points: 0        \nVariables:\n\t0\ttime\ttime\n\t1\tv(in)\tvoltage\n\t2\tv(out)\tvoltage\nBinary:\n'

    def read(self,rows,header=None,extra=b'',stop=200e-12):
        with tempfile.TemporaryDirectory() as directory:
            raw=Path(directory)/'bench.raw'
            data=(self.header if header is None else header)+b''.join(struct.pack('<3d',*row) for row in rows)+extra
            raw.write_bytes(data);result=p.read_prefix(raw,stop)
            self.assertEqual(raw.read_bytes(),data)
            return result

    def test_every_vector_and_complete_record_payload_is_preserved(self):
        rows=[(0.,0.,1.8),(100e-12,1e-12,1.80001),(199e-12,0.,1.79999),(201e-12,0.,1.8)]
        header,copied,report=self.read(rows,extra=b'partial')
        end=copied.index(b'Binary:\n')+8
        self.assertEqual(header,self.header)
        self.assertEqual(copied[end:],b''.join(struct.pack('<3d',*r) for r in rows[:3]))
        self.assertEqual(report['copied_frames'],3);self.assertEqual(report['native_vectors'],3)
        self.assertEqual(report['ignored_partial_source_frame_bytes'],7)
        self.assertEqual(report['last_copied_ps'],199.)
        self.assertFalse(report['qualified_phy']);self.assertFalse(report['source_waveform_complete'])

    def test_only_the_copied_header_point_count_changes(self):
        _,copied,_=self.read([(0.,0.,1.8),(200e-12,0.,1.8),(300e-12,0.,1.8)])
        header=copied[:copied.index(b'Binary:\n')+8]
        self.assertIn(b'No. Points: 2\n',header)
        scrub=lambda b:re.sub(rb'(?m)^No\. Points:[^\n]*',b'No. Points: <count>',b)
        self.assertEqual(scrub(header),scrub(self.header))

    def test_reject_missing_start_nonfinite_or_nonmonotonic_prefix(self):
        for rows in ([(1e-12,0.,1.8),(300e-12,0.,1.8)],
                     [(0.,0.,1.8),(100e-12,float('nan'),1.8),(300e-12,0.,1.8)],
                     [(0.,0.,1.8),(100e-12,0.,1.8),(90e-12,0.,1.8),(300e-12,0.,1.8)]):
            with self.assertRaises(ValueError):self.read(rows)
        with self.assertRaises(ValueError):self.read([(0.,0.,1.8),(100e-12,0.,1.8)])
        with self.assertRaises(ValueError):self.read([(0.,0.,1.8),(300e-12,0.,1.8)],stop=250e-12)

    def test_reject_ambiguous_or_complex_vector_tables(self):
        rows=[(0.,0.,1.8),(300e-12,0.,1.8)]
        for header in (self.header.replace(b'Flags: real',b'Flags: complex'),
                       self.header.replace(b'\t2\tv(out)',b'\t2\tv(in)'),
                       self.header.replace(b'\t2\tv(out)',b'\t3\tv(out)'),
                       self.header.replace(b'No. Points: 0',b'No. Points: 0\nNo. Points: 0')):
            with self.assertRaises(ValueError):self.read(rows,header)


if __name__=='__main__':unittest.main()
