# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_native_clock_release_v2 as diagnosis


class NativeClockFailureLocalizationTests(unittest.TestCase):
    def test_nearest_saved_terminal_uses_the_actual_resistor_network(self):
        body=[l.split() for l in ['R0 Y n 1 $ output wire','R1 n Y.t0 10','R2 n Y.t1 2',
            'X0 Y.t0 A VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15',
            'X1 Y.t1 A VPWR VPWR sky130_fd_pr__pfet_01v8 w=1 l=.15']]
        self.assertEqual(diagnosis.sense_node(body,'Y'),('Y.t1',3.))
        with self.assertRaises(ValueError):diagnosis.sense_node(body,'disconnected')

    def test_memory_mapped_reader_rejects_unfinished_raw_without_copying_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bench.raw';head=b'Title: test\nFlags: real\nNo. Variables: 2\nNo. Points: 2\nVariables:\n0 time time\n1 v(q) voltage\nBinary:\n'
            p.write_bytes(head+np.array([[0.,0.],[1e-9,1.8]],dtype='<f8').tobytes())
            names,w=diagnosis.read_mapped(p);self.assertEqual(names,['time','v(q)']);self.assertIsInstance(w,np.memmap)
            self.assertAlmostEqual(float(w[1,1]),1.8);del w
            p.write_bytes(p.read_bytes()[:-1])
            with self.assertRaises(ValueError):diagnosis.read_mapped(p)


if __name__=='__main__':unittest.main()
