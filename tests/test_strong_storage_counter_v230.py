# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_strong_storage_counter_v230 as p
import native_bank_inventory_v51 as inventory


class StrongStorageCounterTopology(unittest.TestCase):
    def material(self):
        parent=p.ROOT/'build/diagnostics/direct_feedback_counter_physical_v212/60b8e6502370d672'
        component=p.ROOT/'build/diagnostics/strong_counter_storage_bodytap_v229/cf710f8369c0d418'
        if not (component/'summary.json').exists():self.skipTest('requires actual qualified NAND8 body-contact row')
        i=json.loads((parent/'manifest.json').read_text())['identity'];si=json.loads((component/'manifest.json').read_text())['identity'];r=json.loads((component/'summary.json').read_text())
        row=dict(r['physical'],ports=si['anchors'],macro=p.STORAGE,gds_sha256=r['extraction']['gds_sha256'],lef_sha256=p.sha(component/(p.STORAGE+'.lef')))
        cells=p.strengthened_cells(i['cells']);macros=deepcopy(i['macros']);macros[p.STORAGE]=p.original.macro(p.STORAGE,component,row)
        macros={name:macros[name] for name in {c['model'] for c in cells}}
        return i,cells,macros

    def test_only_storage_models_and_one_parallel_request_buffer_change(self):
        i,cells,macros=self.material();self.assertEqual(len(cells),22)
        old={c['name']:c for c in i['cells']};new={c['name']:c for c in cells}
        self.assertEqual(set(new)-set(old),{'request_driver_parallel'})
        for name,c in old.items():self.assertEqual(new[name],dict(c,model=p.STORAGE) if name in p.Q_TAGS else c)
        parallel=dict(new['request_driver_parallel'],name='request_driver');self.assertEqual(parallel,old['request_driver'])
        ports,devices=inventory.native_leaves(p.original.source(cells,macros),p.NAME)
        self.assertEqual(ports,p.PORTS);self.assertEqual(len(devices),598)
        self.assertEqual({m:sum(d['model']==m for d in devices) for m in {d['model'] for d in devices}},
            {'sky130_fd_pr__nfet_01v8':274,'sky130_fd_pr__pfet_01v8_hvt':274,'sky130_fd_pr__cap_mim_m3_1':50})
        with self.assertRaises(ValueError):p.strengthened_cells(i['cells'][:-1])
        with self.assertRaises(ValueError):p.strengthened_cells(cells)

    def test_actual_native_boxes_fit_and_all_three_low_feedbacks_use_native_accesses(self):
        i,cells,macros=self.material();plan=p.strong_plan(cells,macros,p.original.default_plan())
        self.assertEqual({d['net'] for d in plan['direct_feedback']},{'low0_qb','low1_qb','low2_qb'})
        for d in plan['direct_feedback']:
            stage=d['net'][:-3];self.assertEqual([(e['cell'],e['pin']) for e in d['ends']],[(stage+'_q','B'),(stage+'_b','Y')])
            self.assertNotIn(d['net'],plan['points']);self.assertNotIn(d['net'],plan['buses'])
        for net,x in (('REQUEST',6.5),('request_i',2.)):
            ends=[e for e in plan['points'][net] if e['cell'].startswith('request_driver')]
            self.assertEqual(len(ends),2);self.assertTrue(all(e['x']==x for e in ends))
        boxes=[]
        for c in cells:
            t=plan['placements'][c['name']];a,b,d,e=macros[c['model']]['bbox'];boxes.append((c['name'],(a+t['x'],b+t['y'],d+t['x'],e+t['y'])))
        for k,(name,(a,b,d,e)) in enumerate(boxes):
            for other,(f,g,h,j) in boxes[k+1:]:self.assertFalse(max(a,f)<min(d,h) and max(b,g)<min(e,j),(name,other))


if __name__=='__main__':unittest.main()
