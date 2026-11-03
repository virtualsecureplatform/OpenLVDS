# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from assemble_driver_compact_native import observations


class CompactNativeObservationBinding(unittest.TestCase):
    def test_fresh_conductor_equivalence_uses_existing_named_rc_node(self):
        ext='''node "conductor" 0 1.0 100 200 metal4
equiv "conductor" "I8.Y"
equiv "I8.Y" "I8.IP.I0.D0"
'''
        model='''R0 conductor conductor.n1 4.0
C0 conductor.n1 VSS 1e-15
'''
        target=dict(physical_pin='I8.Y',cell='inv',members=['original'])
        result=observations(ext,model,dict(DP=target))['DP']
        self.assertEqual(result['native_node'],'conductor')
        self.assertEqual(result['gds_anchor'],dict(x_grid=100,y_grid=200,layer='metal4'))
        self.assertEqual(result['physical_pin'],'I8.Y')
        with self.assertRaises(ValueError):
            observations(ext,model.replace('conductor ', 'conductor.t0 '),dict(DP=target))

    def test_missing_ambiguous_or_merged_observations_rejected(self):
        ext='''node "conductor" 0 1 100 200 metal4
equiv "conductor" "I8.Y"
equiv "conductor" "I18.Y"
'''
        model='R0 conductor other 1\n'
        target=lambda p:dict(physical_pin=p)
        with self.assertRaises(ValueError): observations(ext,model,dict(DP=target('absent')))
        with self.assertRaises(ValueError):
            observations(ext,model,dict(DP=target('I8.Y'),DN=target('I18.Y')))
        ambiguous=ext+'node "other" 0 1 300 400 metal4\nequiv "conductor" "other"\n'
        with self.assertRaises(ValueError):observations(ambiguous,model,dict(DP=target('I8.Y')))
