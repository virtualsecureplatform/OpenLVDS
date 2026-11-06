# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_compact_repaired_counter_v205 as p


class DedicatedRequestCounterPlanning(unittest.TestCase):
    def test_union_spine_length_does_not_double_count_shared_clock(self):
        cells=[dict(name='a',model='gate'),dict(name='b',model='gate'),dict(name='c',model='gate')]
        macros={'gate':dict(row=dict(ports={'A':dict(y_um=0)}))}
        places={n:dict(x=0,y=y) for n,y in zip(('a','b','c'),(0,5,15))}
        points={'CLK':[dict(cell=n,pin='A',x=1) for n in ('a','b','c')]}
        self.assertEqual(p.wire_spans(cells,macros,places,points,{'CLK':10}),{'CLK':15.})
        points['CLK'].append(dict(cell='b',pin='A',x=2))
        self.assertEqual(p.wire_spans(cells,macros,places,points,{'CLK':10}),{'CLK':20.})

    def test_actual_native_macros_fit_without_overlap_and_global_spines_shorten(self):
        path=p.ROOT/'build/diagnostics/repaired_clock_counter_physical_v191/e2af7f307ddb041d/manifest.json'
        if not path.exists():self.skipTest('requires retained exact 21-macro counter manifest')
        i=json.loads(path.read_text())['identity'];c=p.compact_plan(i['cells'],i['macros'],i['configuration'])
        self.assertEqual(len(c['placements']),21);self.assertEqual(set(c['placements']),set(i['placements']))
        boxes=[]
        for cell in i['cells']:
            position=c['placements'][cell['name']];a,b,d,e=i['macros'][cell['model']]['bbox'];x,y=position['x'],position['y']
            boxes.append((cell['name'],(a+x,b+y,d+x,e+y)))
        for n,(name,(a,b,d,e)) in enumerate(boxes):
            for other,(f,g,h,j) in boxes[n+1:]:
                self.assertFalse(max(a,f)<min(d,h) and max(b,g)<min(e,j),(name,other))
        before=p.wire_spans(i['cells'],i['macros'],i['placements'],i['points'],i['buses'])
        after=p.wire_spans(i['cells'],i['macros'],c['placements'],c['points'],c['buses'])
        self.assertLess(after['CLK'],.65*before['CLK']);self.assertLess(after['request_i'],.45*before['request_i'])
        ys=sorted(c['buses'].values());self.assertTrue(all(b-a>=4 for a,b in zip(ys,ys[1:])))
        changed=[(net,a,b) for net in i['points'] for a,b in zip(i['points'][net],c['points'][net]) if a!=b]
        self.assertEqual({net for net,a,b in changed},{'REQUEST','request_i'})
        self.assertTrue(all(a['cell']==b['cell']=='request_driver' and a['pin']==b['pin'] for net,a,b in changed))
        p.require_spine_clearance(i['cells'],i['macros'],c['placements'],c['points'],c['buses'],c['configuration'])
        import build_compact_repaired_counter_v202 as failed
        old=failed.compact_plan(i['cells'],i['macros'],i['configuration'])
        with self.assertRaisesRegex(ValueError,'spine clearance'):
            p.require_spine_clearance(i['cells'],i['macros'],old['placements'],old['points'],old['buses'],old['configuration'])


if __name__=='__main__':unittest.main()
