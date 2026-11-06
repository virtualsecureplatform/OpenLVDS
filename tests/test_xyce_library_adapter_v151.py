# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import benchmark_xyce_measured_fine_v151 as p


class XyceLibraryAdapterTests(unittest.TestCase):
    def test_only_comments_change_across_multiple_independent_rc_namespaces(self):
        text='* native library\n.subckt first A B\nR0 A 1 0.123 $ position\nC0 1 B 0.0312f $ **FLOATING\nX0 A A B B sky130_fd_pr__nfet_01v8 w=.65 l=.15 ad=.1 as=.1 pd=1 ps=1\n.ends first\n.subckt second A B\nR0 A 1 12\nC0 1 B 5f $ another annotation\n.ends second\n'
        original=text;adapted=p.library_adapter(text)
        self.assertNotIn('$',adapted);self.assertIn('R0 A 1 0.123',adapted);self.assertIn('R0 A 1 12',adapted)
        self.assertEqual(adapted.count('.subckt'),2);self.assertEqual(text,original)
        self.assertEqual(p.library_adapter(adapted),adapted)
        self.assertEqual([line.split('$',1)[0].split() for line in text.splitlines()],[line.split() for line in adapted.splitlines()])


if __name__=='__main__':unittest.main()
