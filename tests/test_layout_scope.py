# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import draw_macro,erc,circuits,flatten,rows_geometry,split_rows


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

    def test_released_macros_have_no_static_electrical_violations(self):
        defs=circuits((Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text())
        for top in ['openlvds_io_tx','openlvds_io_rx']:
            self.assertEqual(erc(*flatten(defs,top)),[],top)

    def test_erc_detects_domain_body_and_floating_gate_errors(self):
        n,p='sky130_fd_pr__nfet_01v8','sky130_fd_pr__pfet_01v8'
        device=lambda name,model,nodes:dict(name=name,model=model,nodes=nodes,params=dict(w='1',l='0.15'))
        errors=erc(['A','Y','VDDD','VDDIO','VSS'],[device('P',p,['Y','A','VDDIO','VDDIO']),device('N',n,['Y','F','VSS','Y'])])
        text=' '.join(errors)
        for expected in ['1.8 V device on VDDIO','PMOS well','NMOS body','floating gate','VDDD: unconnected pin']:
            self.assertIn(expected,text)

    def test_rows_keep_every_device_and_join_split_nets_with_trunks(self):
        model='sky130_fd_pr__nfet_01v8'
        info=dict(bbox=[-1,-2,1,2],ports={n:('metal1',x,y) for n,x,y in [('D',-.5,0),('G',0,1),('S',.5,0),('B',0,-1)]})
        library={(model,2.,.15):('nfet',info)}
        devices=[dict(name=f'N{i}',model=model,nodes=[f'J{i+1}',f'J{i}','VSS','VSS'],params=dict(w='2',l='0.15')) for i in range(12)]
        ports=['J0','J12','VSS']
        rows=split_rows(devices,library,3)
        self.assertEqual(sorted(d['name'] for row in rows for d in row),sorted(d['name'] for d in devices))
        geometry,uses,labels,public,width,height,nets,count,hints=rows_geometry(ports,devices,library,3)
        self.assertEqual(hints,[])
        self.assertEqual((len(uses),count),(12,3))
        self.assertEqual(set(public),set(ports))
        # VSS is in every row: one full-height metal4 strap labelled as the pin.
        strap=[l for l in labels if l[0]=='VSS' and l[5]]
        self.assertEqual(len(strap),1);self.assertAlmostEqual(strap[0][4],height)
        with self.assertRaises(ValueError):rows_geometry(['MISSING']+ports,devices,library,3)

    def test_narrow_poly_resistors_get_full_width_rpm(self):
        model='sky130_fd_pr__res_high_po_0p35'
        info=dict(bbox=[-1,-4,1,4],resistor=[-.175,-2.705,.175,2.705],ports={n:('metal1',0,y) for n,y in [('R1',2.5),('R2',-2.5),('B',-3.3)]})
        library={(model,.35,1.25):('res',info)}
        devices=[dict(name=f'R{i}',model=model,nodes=[f'N{i}',f'N{i+1}','VSS'],params=dict(w='0.35',l='1.25')) for i in range(3)]
        hints=rows_geometry(['N0','N3','VSS'],devices,library,1)[8]
        self.assertEqual(len(hints),3)
        for x0,y0,x1,y1 in hints:
            self.assertAlmostEqual(x1-x0,1.27);self.assertAlmostEqual(y1-y0,5.81)
        # rpm.2: neighbouring implants stay at least 0.84 um apart.
        self.assertGreaterEqual(min(b[0]-a[2] for a,b in zip(hints,hints[1:])),.84)

    def test_row_breaks_avoid_cutting_speed_critical_nets(self):
        model='sky130_fd_pr__nfet_g5v0d10v5'
        info=dict(bbox=[-1,-2,1,2],ports={n:('metal1',x,y) for n,x,y in [('D',-.5,0),('G',0,1),('S',.5,0),('B',0,-1)]})
        library={(model,2.,.5):('nfet',info)}
        device=lambda name,gate:dict(name=name,model=model,nodes=['OUT',gate,'VSS','VSS'],params=dict(w='2',l='0.5'))
        # Two groups of unequal size: equal-width splitting would cut the second group's gate net.
        devices=[device(f'L{i}','top__GPL') for i in range(7)]+[device(f'R{i}','top__GPR') for i in range(13)]
        rows=split_rows(devices,library,2,['OUT','VSS'])
        self.assertEqual([len(r) for r in rows],[7,13])
        self.assertEqual({d['nodes'][1] for d in rows[0]},{'top__GPL'});self.assertEqual({d['nodes'][1] for d in rows[1]},{'top__GPR'})
        self.assertEqual(sum(map(len,split_rows(devices,library,5,['OUT','VSS']))),20)

    def test_fast_internal_nets_take_the_nearest_tracks_and_supplies_the_farthest(self):
        model='sky130_fd_pr__nfet_g5v0d10v5'
        info=dict(bbox=[-1,-2,1,2],ports={n:('metal1',x,y) for n,x,y in [('D',-.5,0),('G',0,1),('S',.5,0),('B',0,-1)]})
        library={(model,2.,.5):('nfet',info)}
        device=lambda name,d,g:dict(name=name,model=model,nodes=[d,g,'VSS','VSS'],params=dict(w='2',l='0.5'))
        devices=[device('A','top__X','IN'),device('B','top__GPL','top__X'),device('C','OUT','top__GPL')]
        geometry,uses,labels,public,width,height,nets,count,hints=rows_geometry(['IN','OUT','VSS'],devices,library,1)
        # Bus y of each net is the y of its wide horizontal metal3 rectangle.
        buses=sorted((r[1],r[3]-r[1]) for r in geometry.layers['metal3'] if r[2]-r[0]>r[3]-r[1])
        heights=[h for _,h in buses]
        self.assertEqual(heights[-1],1000)                     # 5 um supply bus is the farthest track
        self.assertTrue(all(h==80 for h in heights[:-1]))      # 0.4 um signal buses below it
        label_y={l[0]:l[2] for l in labels if l[6]=='metal3'}
        self.assertLess(label_y['top__GPL'],label_y['top__X']) # listed fast net is nearer the devices


if __name__=='__main__':unittest.main()
