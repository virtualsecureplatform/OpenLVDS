# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from spice_scope import closure_hash

class CircuitScope(unittest.TestCase):
    def test_unused_changes_do_not_invalidate_a_reference(self):
        lib='.subckt parent A B\nX1 A B child\n.ends parent\n.subckt child A B\nR1 A B 10\n.ends child\n.subckt unused A B\nR1 A B 20\n.ends unused\n'
        original=closure_hash(lib,'parent')
        self.assertEqual(original,closure_hash(lib.replace('20','30'),'parent'))
        self.assertNotEqual(original,closure_hash(lib.replace(' 10',' 11'),'parent'))

if __name__=='__main__':unittest.main()
