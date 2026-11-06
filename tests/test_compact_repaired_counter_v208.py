# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_compact_repaired_counter_v208 as p


class SeparatedViaBandCounterPlanning(unittest.TestCase):
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
        i=json.loads(path.read_text())['identity']
        with self.assertRaisesRegex(ValueError,'high2_qb / low2_qb'):
            p.compact_plan(i['cells'],i['macros'],i['configuration'])



if __name__=='__main__':unittest.main()
