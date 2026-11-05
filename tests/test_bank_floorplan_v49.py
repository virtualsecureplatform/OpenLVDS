# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bank_floorplan_v49 as floor


class TappedFloorplanTests(unittest.TestCase):
    def fixture(self):
        logic=floor.SC+'buf_1';records={m:dict(size_um=[w,2.72]) for m,w in [(floor.TAP,.46),(floor.FILL,.46),(logic,1.38)]}
        models=[floor.FILL,floor.TAP,logic,floor.TAP,floor.FILL];x=0;cells=[];places={}
        for i,m in enumerate(models):
            n='cell'+str(i);cells.append(dict(name=n,model=m,pins=dict(VPWR='VPWR',VGND='VGND',VPB='VPWR',VNB='VGND')))
            places[n]=[round(x,6),0.];x+=records[m]['size_um'][0]
        groups=[dict(cells=[c['name'] for c in cells],origin_um=[0.,0.],width_um=round(x,6))]
        return cells,places,records,groups

    def test_continuous_tapped_row_and_actual_site_grid(self):
        cells,places,records,groups=self.fixture()
        floor.validate_groups(cells,places,records,groups)
        self.assertEqual(len(floor.validate(cells,places,records,[0,0,10,10])),5)

    def test_shifted_well_row_gap_is_rejected(self):
        c,p,r,g=self.fixture();p['cell2'][0]+=.46
        with self.assertRaisesRegex(ValueError,'physical gap'):floor.validate_groups(c,p,r,g)

    def test_missing_tap_and_wrong_body_domain_are_rejected(self):
        c,p,r,g=self.fixture();bad=deepcopy(c);bad[1]['model']=floor.FILL
        with self.assertRaisesRegex(ValueError,'two well taps'):floor.validate_groups(bad,p,r,g)
        c[2]['pins']['VPB']='VGND'
        with self.assertRaisesRegex(ValueError,'wrong domain'):floor.validate_groups(c,p,r,g)

    def test_overlapping_off_grid_and_outside_cells_are_rejected(self):
        c,p,r,g=self.fixture();bad=deepcopy(p);bad['cell2'][0]=.46
        with self.assertRaisesRegex(ValueError,'overlap'):floor.validate(c,bad,r,[0,0,10,10])
        bad=deepcopy(p);bad['cell2'][0]+=.005
        with self.assertRaisesRegex(ValueError,'site grid'):floor.validate(c,bad,r,[0,0,10,10])
        with self.assertRaisesRegex(ValueError,'outside die'):floor.validate(c,p,r,[0,0,1,1])

    def test_untapped_or_duplicated_row_members_are_rejected(self):
        c,p,r,g=self.fixture();bad=deepcopy(g);bad.append(deepcopy(g[0]))
        with self.assertRaisesRegex(ValueError,'outside its tapped'):floor.validate_groups(c,p,r,bad)


if __name__=='__main__':unittest.main()
