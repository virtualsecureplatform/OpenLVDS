# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_binary_raw_v2 import read,validate
from run_native_binary_v2 import translate


class NativeBinaryTests(unittest.TestCase):
    def test_complete_missing_truncated_and_nonfinite_vectors(self):
        header=b'Flags: real\nNo. Variables: 2\nNo. Points: 2\nVariables:\n0 time time\n1 v(out) voltage\nBinary:\n'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'wave.raw';p.write_bytes(header+struct.pack('<dddd',0,0,1e-9,1.8))
            names,w=validate(p,['v(out)'],1e-9);self.assertEqual(names,['time','v(out)']);self.assertEqual(w[1,1],1.8)
            with self.assertRaisesRegex(ValueError,'Missing requested'):validate(p,['v(other)'],1e-9)
            p.write_bytes(p.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError,'Incomplete'):read(p)
            p.write_bytes(header+struct.pack('<dddd',0,0,1e-9,float('nan')))
            with self.assertRaisesRegex(ValueError,'Nonfinite'):validate(p,['v(out)'],1e-9)

    def test_translation_preserves_models_solver_tolerances_and_stop_time(self):
        original='Native\n.lib "model" ss\n.options device temp=40\n.options timeint method=gear reltol=1e-4\n.tran 2p 20n 0 2p\n.print tran V(IN) V(XD:a.t0)\n.end\n'
        text,names=translate(original)
        self.assertIn('.lib "model" ss',text);self.assertIn('.options method=gear reltol=1e-4',text)
        self.assertIn('.tran 2p 20n 0 2p',text);self.assertIn('.temp 40',text)
        self.assertEqual(names,['v(in)','v(xd.a.t0)']);self.assertIn('.save v(in) v(xd.a.t0)',text.lower())
        with self.assertRaises(ValueError):translate(original.replace('V(IN)','I(IN)'))


if __name__=='__main__':unittest.main()
