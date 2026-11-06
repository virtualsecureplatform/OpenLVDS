# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_direct_feedback_counter_v212 as p
import build_compact_repaired_counter_v210 as compact


class NativeLocalFeedback(unittest.TestCase):
    def setUp(self):
        path=p.ROOT/'build/diagnostics/repaired_clock_counter_physical_v191/e2af7f307ddb041d/manifest.json'
        if not path.exists():self.skipTest('requires retained exact native counter cells and accesses')
        self.i=json.loads(path.read_text())['identity']

    def test_exact_feedback_pins_replace_only_first_loop_bus(self):
        i=self.i;a=compact.compact_plan(i['cells'],i['macros'],i['configuration']);b=p.compact_plan(i['cells'],i['macros'],i['configuration'])
        self.assertEqual(a['placements'],b['placements']);self.assertEqual(a['configuration'],b['configuration'])
        self.assertEqual({k:v for k,v in a['points'].items() if k!='low0_qb'},b['points'])
        self.assertEqual({k:v for k,v in a['buses'].items() if k!='low0_qb'},b['buses'])
        d=b['direct_feedback'];self.assertEqual(d['net'],'low0_qb');self.assertEqual(d['layer'],'metal4')
        self.assertEqual([(e['cell'],e['pin']) for e in d['ends']],[('low0_q','B'),('low0_b','Y')])
        start,end=d['ends'];self.assertAlmostEqual(start['x_um'],121.98);self.assertAlmostEqual(end['x_um'],165.34)
        self.assertAlmostEqual(start['y_um'],11.4);self.assertAlmostEqual(end['y_um'],12.08)
        length=end['x_um']-start['x_um']+end['y_um']-start['y_um'];self.assertAlmostEqual(length,44.04)

    def test_changed_fanout_net_or_native_access_refused(self):
        i=self.i;plan=compact.compact_plan(i['cells'],i['macros'],i['configuration'])
        for tag,pin in [('low0_q','B'),('low0_b','Y')]:
            cells=deepcopy(i['cells']);next(c for c in cells if c['name']==tag)['pins'][pin]='other'
            with self.subTest(tag=tag),self.assertRaises(ValueError):p.feedback_accesses(cells,i['macros'],plan['placements'])
        cells=deepcopy(i['cells']);next(c for c in cells if c['name']=='high1_b')['pins']['B']='low0_qb'
        with self.assertRaises(ValueError):p.feedback_accesses(cells,i['macros'],plan['placements'])
        macros=deepcopy(i['macros']);model=next(c for c in i['cells'] if c['name']=='low0_q')['model'];macros[model]['row']['ports']['B']['layer']='metal4'
        with self.assertRaises(ValueError):p.feedback_accesses(i['cells'],macros,plan['placements'])


if __name__=='__main__':unittest.main()
