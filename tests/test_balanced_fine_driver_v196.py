# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_balanced_fine_driver_v196 as p


class BalancedDriverTopology(unittest.TestCase):
    def test_all_fingers_have_exact_native_inverter_connections(self):
        for s in p.PROFILES:
            ports,devices=p.inventory.native_leaves(p.schematic(s),p.name(s));self.assertEqual(ports,p.PORTS)
            self.assertEqual(len(devices),s['p_fingers']+s['n_fingers']+1)
            for d in devices:
                if 'nfet' in d['model']:self.assertEqual(d['nodes'],['Y','A','VGND','VGND']);self.assertEqual(d['params'],dict(w='0.65',l='.15'))
                elif 'pfet' in d['model']:self.assertEqual(d['nodes'],['Y','A','VPWR','VPWR']);self.assertEqual(d['params'],dict(w='1.0',l='.15'))
                else:self.assertEqual(d['model'],p.CAP);self.assertEqual(d['nodes'],['Y','VGND']);self.assertEqual(d['params'],dict(w='2',l='2'))
            self.assertAlmostEqual(s['p_fingers']/(s['n_fingers']*.65),20/6.5)

    def test_actual_compact_finger_metadata_routes_every_diffusion_and_body(self):
        parent=p.ROOT/'build/diagnostics/balanced_driver_pcells_v195/508ff6e991c53541'
        if not (parent/'summary.json').exists():self.skipTest('requires actual native multi-finger metadata')
        rows=json.loads((parent/'summary.json').read_text())['rows'];by={(r['spec']['kind'],r['spec']['fingers']):r for r in rows}
        cap=dict(bbox=[-1,-1,3,3],ports=dict(C1=('metal4',1,1),C2=('metal3',-.5,1)))
        for s in p.PROFILES:
            selected={k:by[k,s[k+'_fingers']] for k in ('n','p')};g,places,ports=p.straps(s,selected,cap)
            self.assertEqual(set(ports),set(p.PORTS));self.assertEqual(set(places),{'n','p','cap'})
            self.assertEqual(places['p']['y']-places['n']['y'],8.)
            self.assertGreater(places['cap']['x']+cap['bbox'][0],places['p']['x']+selected['p']['geometry']['bbox'][2])
            self.assertTrue(all(layer in g.layers for layer in ('metal1','metal2','metal3','metal4','viali','via1','via2','via3')))
            self.assertEqual(ports['VGND']['layer'],'metal3');self.assertEqual(ports['A']['layer'],'metal4')


if __name__=='__main__':unittest.main()
