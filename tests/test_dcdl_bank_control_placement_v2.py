# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from harden_dcdl_bank_v7 import control_placements,bank


class BankControlPlacementTests(unittest.TestCase):
    def test_all_controls_fit_on_site_grid_above_the_fixed_fine_macros(self):
        cells=[c for c in bank.instances() if c['model'].startswith(bank.native.SC)]
        widths={c['model']:3.22 for c in cells};p=control_placements(widths)
        self.assertEqual(set(p),{c['name'] for c in cells});self.assertEqual(len(p),78)
        boxes=[]
        for c in cells:
            x,y=p[c['name']]['location'];w=widths[c['model']]
            self.assertGreaterEqual(y,116.96);self.assertLessEqual(y+2.72,130.56);self.assertLessEqual(x+w,147.2)
            self.assertAlmostEqual(x/.46,round(x/.46),places=6);self.assertAlmostEqual(y/2.72,round(y/2.72),places=6)
            boxes.append((x,y,x+w,y+2.72))
        for n,a in enumerate(boxes):
            for b in boxes[n+1:]:self.assertFalse(max(a[0],b[0])<min(a[2],b[2]) and max(a[1],b[1])<min(a[3],b[3]))


if __name__=='__main__':unittest.main()
