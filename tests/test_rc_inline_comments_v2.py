# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit


class RcInlineCommentTests(unittest.TestCase):
    def test_parasitic_comments_do_not_keep_fake_caps_in_the_topology_audit(self):
        text='.subckt cell A Y G\nR0 A a.t0 1 $ route\nC0 a.t0 G 2f $ **FLOATING\nX0 Y a.t0 G G sky130_fd_pr__nfet_01v8 w=1 l=.15\nXC Y G sky130_fd_pr__cap_mim_m3_1 w=2 l=2\n.ends cell\n'
        result=collapse(text);self.assertNotIn('R0',result);self.assertNotIn('C0',result)
        self.assertIn('X0 Y A G G',result);self.assertIn('XC Y G sky130_fd_pr__cap_mim_m3_1',result)
        self.assertTrue(audit(text)['elementwise_passive_passed'])


if __name__=='__main__':unittest.main()
