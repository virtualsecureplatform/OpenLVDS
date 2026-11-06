# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import struct,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import xyce_raw_aliases_v148 as p


class XyceRawAliasTests(unittest.TestCase):
    def raw(self,names=('TIME','V(XD:X0.A)','V(OUT)'),flags='real'):
        header='Title: raw probe\nFlags: '+flags+'\nNo. Variables: 3\nNo. Points: 2\nVariables:\n'+''.join(f'\t{k}\t{name}\tvoltage\n' for k,name in enumerate(names))+'Binary:\n'
        return header.encode()+struct.pack('<6d',0.,0.,1.,20e-9,1.8,0.)

    def test_normalization_changes_only_header_aliases_and_preserves_exact_samples(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.raw';target=Path(temp)/'normalized.raw';data=self.raw();source.write_bytes(data)
            r=p.normalize(source,target)
            self.assertIn(b'v(xd.x0.a)',target.read_bytes());self.assertTrue(r['binary_samples_byte_identical'])
            self.assertEqual(target.read_bytes().split(b'Binary:\n',1)[1],data.split(b'Binary:\n',1)[1])
            self.assertEqual(source.read_bytes(),data);self.assertEqual((r['samples'],r['variables']),(2,3))
            with self.assertRaises(FileExistsError):p.normalize(source,target)

    def test_alias_collisions_and_wrong_indices_are_refused_before_creating_output(self):
        for data in [self.raw(('TIME','V(XD:A)','V(XD.A)')),self.raw().replace(b'\t2\tV(OUT)',b'\t1\tV(OUT)')]:
            with self.subTest(data=data[:20]),tempfile.TemporaryDirectory() as temp:
                source=Path(temp)/'source';target=Path(temp)/'target';source.write_bytes(data)
                with self.assertRaises(ValueError):p.normalize(source,target)
                self.assertFalse(target.exists())

    def test_complex_and_incomplete_payload_are_refused(self):
        for data in [self.raw(flags='complex'),self.raw()[:-1]]:
            with self.subTest(data=data[:20]),tempfile.TemporaryDirectory() as temp:
                source=Path(temp)/'source';source.write_bytes(data)
                with self.assertRaises(ValueError):p.normalize(source,Path(temp)/'target')


if __name__=='__main__':unittest.main()
