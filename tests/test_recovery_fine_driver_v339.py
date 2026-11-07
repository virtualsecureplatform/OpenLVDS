# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_recovery_fine_driver_v339 as p


class StrongDischargeDriverTopology(unittest.TestCase):
    def test_all_fingers_have_exact_native_inverter_connections(self):
        for s in p.PROFILES:
            ports,devices=p.inventory.native_leaves(p.schematic(s),p.name(s));self.assertEqual(ports,p.PORTS)
            self.assertEqual(len(devices),s['p_fingers']+s['n_fingers']+1)
            for d in devices:
                if 'nfet' in d['model']:self.assertEqual(d['nodes'],['Y','A','VGND','VGND']);self.assertEqual(d['params'],dict(w='0.65',l='.15'))
                elif 'pfet' in d['model']:self.assertEqual(d['nodes'],['Y','A','VPWR','VPWR']);self.assertEqual(d['params'],dict(w='1.0',l='.15'))
                else:self.assertEqual(d['model'],p.CAP);self.assertEqual(d['nodes'],['Y','VGND']);self.assertEqual(d['params'],dict(w='2',l='2'))
            self.assertAlmostEqual(s['p_fingers']/(s['n_fingers']*.65),s['p_fingers']/10.4)

    def test_actual_compact_finger_metadata_routes_every_diffusion_and_body(self):
        parent=p.ROOT/'build/diagnostics/recovery_driver_pcells_v338/e292902d8c9c4b10'
        if not (parent/'summary.json').exists():self.skipTest('requires actual native multi-finger metadata')
        rows=json.loads((parent/'summary.json').read_text())['rows'];by={(r['spec']['kind'],r['spec']['fingers']):r for r in rows}
        capfile=p.ROOT/'build/diagnostics/balanced_fine_driver_physical_v196/d6bcddc075ec0d7a/openlvds_balanced_p20n10_v196/balanced_guard2_v196.mag'
        if not capfile.exists():self.skipTest('requires retained actual native MIM terminal geometry')
        cap=p.layout.pcell_info(capfile)
        for s in p.PROFILES:
            selected={}
            for k in ('n','p'):
                row=by[k,s[k+'_fingers']];src=parent/row['top'];terminals,witness=p.contacts.complete_accesses(row,(src/(row['top']+'.mag')).read_text(),(src/(row['top']+'.lvs.spice')).read_text())
                self.assertTrue(witness['native_contact_and_viali_verified']);self.assertFalse(witness['ideal_net_alias_added'])
                self.assertEqual(len([t for t in terminals if t['name'].startswith('D')]),s[k+'_fingers']//2+1)
                selected[k]=dict(row,terminal_accesses=terminals)
            g,places,ports=p.straps(s,selected,cap)
            self.assertEqual(set(ports),set(p.PORTS));self.assertEqual(set(places),{'n','p','cap'})
            self.assertEqual(places['p']['y']-places['n']['y'],8.)
            self.assertGreater(places['cap']['x']+cap['bbox'][0],places['p']['x']+selected['p']['geometry']['bbox'][2])
            self.assertTrue(all(layer in g.layers for layer in ('metal1','metal2','metal3','metal4','viali','via1','via2','via3')))
            self.assertEqual(ports['VGND']['layer'],'metal3');self.assertEqual(ports['A']['layer'],'metal4')
            c1=(places['cap']['x']+cap['ports']['C1'][1],places['cap']['y']+cap['ports']['C1'][2])
            c2=(places['cap']['x']+cap['ports']['C2'][1],places['cap']['y']+cap['ports']['C2'][2])
            def covers(rect,point):return rect[0]*p.layout.GRID<=point[0]<=rect[2]*p.layout.GRID and rect[1]*p.layout.GRID<=point[1]<=rect[3]*p.layout.GRID
            self.assertFalse(any(covers(r,c2) for r in g.layers['metal4']))
            self.assertFalse(any(covers(r,c1) for r in g.layers['metal3']))
            bounds=[places['cap']['x']+cap['bbox'][0],places['cap']['y']+cap['bbox'][1],places['cap']['x']+cap['bbox'][2],places['cap']['y']+cap['bbox'][3]]
            for rect in g.layers['via3']:
                self.assertFalse(max(rect[0]*p.layout.GRID,bounds[0])<min(rect[2]*p.layout.GRID,bounds[2]) and max(rect[1]*p.layout.GRID,bounds[1])<min(rect[3]*p.layout.GRID,bounds[3]))


if __name__=='__main__':unittest.main()
