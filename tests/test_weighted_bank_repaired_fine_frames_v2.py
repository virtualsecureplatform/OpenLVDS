# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import weighted_bank_repaired_fine_frames_v2 as frames


class RepairedFineFrameTests(unittest.TestCase):
    def lef(self,dy=0):
        rows=[]
        for n,y in zip(['NODE','EN','ENB','VDD','VSS'],[10,12,14,16,18]):
            usage='POWER' if n=='VDD' else 'GROUND' if n=='VSS' else 'SIGNAL'
            direction='INOUT' if n in ['VDD','VSS'] else 'INPUT'
            rows.append(f'  PIN {n}\n    DIRECTION {direction} ;\n    USE {usage} ;\n    ANTENNAGATEAREA 0.2 ;\n    PORT\n      LAYER met3 ;\n        RECT 0 {y+dy:.6f} 30 {y+dy+.4:.6f} ;\n    END\n  END {n}\n')
        return ''.join(rows)

    def test_all_five_access_rails_can_be_preserved_by_one_rigid_placement_shift(self):
        self.assertEqual(frames.pin_shift(self.lef(),self.lef(1.68).replace('ANTENNAGATEAREA 0.2','ANTENNAGATEAREA 0.4')),-1.68)

    def test_changed_power_rail_geometry_or_pin_type_cannot_be_hidden_by_signal_alignment(self):
        good=self.lef(1.68)
        for bad in [good.replace('19.680000','19.780000'),good.replace('30 20.080000','29 20.080000'),good.replace('USE GROUND','USE POWER'),good.replace('PIN ENB','PIN WRONG').replace('END ENB','END WRONG')]:
            with self.assertRaises(ValueError):frames.pin_shift(self.lef(),bad)
