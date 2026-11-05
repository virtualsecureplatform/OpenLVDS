# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import physical_cell_adapter_v44 as adapter


class PhysicalCellAdapterTests(unittest.TestCase):
    def lef(self):
        rows=['MACRO fixture','  CLASS BLOCK ;','  ORIGIN 1 1 ;','  SIZE 10 BY 10 ;']
        points=dict(NODE=(-1,-1,0,0),EN=(0,2,1,3),ENB=(2,2,3,3),VDD=(0,4,2,4.6),VSS=(0,6,2,6.6))
        for name,r in points.items():
            rows += ['  PIN '+name,'    PORT','      LAYER met3 ;','        RECT '+' '.join(map(str,r))+' ;']
            if name=='NODE':rows += ['      LAYER met1 ;','        RECT 1 1 2 2 ;']
            rows += ['    END','  END '+name]
        rows += ['  OBS','      LAYER met3 ;','        RECT 8 8 9 9 ;','  END','END fixture','']
        return '\n'.join(rows),points

    def test_aliases_origins_and_pin_roles_are_explicit(self):
        text,points=self.lef();aliases=dict(NODE='A',EN='CTRL',ENB='CTRL_B',VDD='VPWR',VSS='VGND')
        order=['A','CTRL','CTRL_B','VPWR','VGND'];directions={p:'inout' if p in ('A','VPWR','VGND') else 'input' for p in order}
        anchors={p:((r[0]+r[2])/2,(r[1]+r[3])/2) for p,r in points.items()}
        lef,records=adapter.integration_lef(text,'fixture',order,directions,aliases,anchors,[1,1],[11,11],[])
        info=adapter.description(lef,'fixture');self.assertEqual(info['origin'],[0,0]);self.assertEqual(set(info['pins']),set(order))
        self.assertEqual(records['VPWR']['use'],'POWER');self.assertEqual(records['VGND']['use'],'GROUND')
        self.assertEqual(records['A']['direction'],'INOUT');self.assertEqual(records['A']['anchor_um'],[.5,.5])
        self.assertEqual(info['pins']['A'],[('met3',(0.,0.,1.,1.))])
        self.assertIn(('met1',(2.,2.,3.,3.)),adapter.geometry.rectangles(next(adapter.geometry.OBS.finditer(lef))[1]))

    def test_keepout_subtraction_keeps_public_access_and_area(self):
        rect=(0,0,4,4);cut=(1,1,3,3);pieces=adapter.subtract(rect,cut)
        self.assertEqual(sum((r[2]-r[0])*(r[3]-r[1]) for r in pieces),12)
        for r in pieces:self.assertTrue(r[2]<=1 or r[0]>=3 or r[3]<=1 or r[1]>=3)
        self.assertEqual(adapter.subtract(rect,(5,5,6,6)),[rect]);self.assertEqual(adapter.subtract(rect,rect),[])

    def test_bad_alias_and_missing_public_rail_are_rejected(self):
        with self.assertRaises(ValueError):adapter.pins_match({'NODE':[]},{'NODE':'A'},['A','CTRL'])
        text,points=self.lef();aliases={p:p for p in points};dirs={p:'input' for p in points}
        anchors={p:(100,100) for p in points}
        with self.assertRaises(ValueError):adapter.integration_lef(text,'fixture',list(points),dirs,aliases,anchors,[1,1],[11,11],[])

    def test_standard_body_pins_remain_nonrouting_domains(self):
        text='MACRO sc\n  SIZE 1 BY 2 ;\n  ORIGIN 0 0 ;\n  PIN VNB\n    PORT\n      LAYER pwell ;\n        RECT 0 0 1 1 ;\n    END\n  END VNB\n  PIN VPWR\n    PORT\n      LAYER met1 ;\n        RECT 0 1 1 2 ;\n    END\n  END VPWR\nEND sc\n'
        p=adapter.standard_pins(text,'sc',['VNB','VPWR'],dict(VNB='inout',VPWR='inout'))
        self.assertTrue(p['VNB']['well_domain_only']);self.assertFalse(p['VPWR']['well_domain_only'])
        self.assertEqual(p['VNB']['use'],'GROUND');self.assertEqual(p['VPWR']['use'],'POWER')

    def test_junction_pair_signature_allows_only_drain_source_exchange(self):
        source='.subckt c A B VGND\nXN A B VGND VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15 ad=.1 as=.2 pd=1 ps=2\n.ends c\n'
        swapped=source.replace('ad=.1 as=.2 pd=1 ps=2','ad=.2 as=.1 pd=2 ps=1')
        self.assertEqual(adapter.parameter_signature(source),adapter.parameter_signature(swapped))
        self.assertNotEqual(adapter.parameter_signature(source),adapter.parameter_signature(source.replace('ad=.1','ad=.11')))
        with self.assertRaises(ValueError):adapter.parameter_signature(source.replace(' pd=1',''))

    def test_signed_coordinate_translation_is_exact(self):
        self.assertEqual(adapter.translated((-.19,-1.1,12.36,14.3),(.19,1.1)),(0.,0.,12.55,15.4))


if __name__=='__main__':unittest.main()
