# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from stage_phy_candidate import overlay
from spice_scope import closure_hash


class PHYAssembly(unittest.TestCase):
    def test_complete_hierarchy_replaces_previous_interface(self):
        base=('.subckt dll A B C\nX0 A B child\n.ends dll\n'
              '.subckt child A B\nR0 A B 1\n.ends child\n'
              '.subckt driver A B\nR1 A B 2\n.ends driver\n')
        candidate=('.subckt dll A B\nX0 B A child\n.ends dll\n'
                   '.subckt child A B\nR0 A B 3\n.ends child\n')
        result=overlay(base,candidate,'dll',['driver'])
        self.assertEqual(closure_hash(result,'dll'),closure_hash(candidate,'dll'))
        self.assertEqual(closure_hash(result,'driver'),closure_hash(base,'driver'))

    def test_shared_helper_change_cannot_silently_alter_receiver(self):
        base=('.subckt dll A B\nX0 A B helper\n.ends dll\n'
              '.subckt rx A B\nX0 A B helper\n.ends rx\n'
              '.subckt helper A B\nR0 A B 1\n.ends helper\n')
        candidate=base.replace('R0 A B 1','R0 A B 2')
        with self.assertRaisesRegex(ValueError,'protected'):
            overlay(base,candidate,'dll',['rx'])
