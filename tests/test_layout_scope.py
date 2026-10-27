# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import draw_macro


class LayoutScope(unittest.TestCase):
    def test_unused_pcells_do_not_move_a_macro(self):
        model='sky130_fd_pr__nfet_01v8'
        ports=['A','Y','VSS']
        devices=[dict(name='N0',model=model,nodes=['J','A','VSS','VSS'],params=dict(w='2',l='0.15')),
                 dict(name='N1',model=model,nodes=['Y','J','VSS','VSS'],params=dict(w='2',l='0.15'))]
        info=dict(bbox=[-1,-2,1,2],ports={n:('metal1',x,y) for n,x,y in
                  [('D',-.5,0),('G',0,1),('S',.5,0),('B',0,-1)]})
        library={(model,2.,.15):('nfet',info)}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=root/'a';b=root/'b';a.mkdir();b.mkdir()
            first=draw_macro(a,'openlvds_delay_line',ports,devices,library)
            library[('unused',1.,1.)]=('unused',dict(bbox=[-1000,-1000,1000,1000],ports={}))
            second=draw_macro(b,'openlvds_delay_line',ports,devices,library)
            self.assertEqual(first,second)
            self.assertEqual((a/'openlvds_delay_line.mag').read_bytes(),(b/'openlvds_delay_line.mag').read_bytes())


if __name__=='__main__':unittest.main()
