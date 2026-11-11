# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_binary_raw_v2 import validate
from xyce_profile_300 import sha

ROOT=Path(__file__).resolve().parents[1]
ARTIFACT=ROOT/'build/diagnostics/model_switching_xyce_300_v5/291b4176c56acf59'


@unittest.skipUnless((ARTIFACT/'summary.json').is_file(),'Build the paired native generic-poly pilot first')
class GenericPolyNative(unittest.TestCase):
    def test_three_geometries_all_fifteen_pvt(self):
        m=json.loads((ARTIFACT/'manifest.json').read_text())
        self.assertEqual(len(m['identity']['specs']),15)
        helper=ROOT/'scripts/generic_poly_xyce_300_v2.py'
        self.assertEqual(sha(helper),m['identity']['inputs']['/work/OpenLVDS/scripts/generic_poly_xyce_300_v2.py'])
        rows=json.loads((ARTIFACT/'summary.json').read_text())['rows']
        self.assertEqual(len(rows),30)
        for index in range(15):
            pair={r['task']['engine']:r for r in rows if r['task']['spec_index']==index}
            self.assertEqual(set(pair),{'xyce','ngspice'})
            arrays={}
            for engine,row in pair.items():
                self.assertTrue(row['complete'])
                self.assertIsNone(row['error'])
                raw=ARTIFACT/row['task']['id']/'bench.raw'
                self.assertEqual(sha(raw),row['files']['bench.raw'])
                names,w=validate(raw,{'v(generic)','v(generic_tie)','v(generic_wide)'},6e-9)
                arrays[engine]=(names,w)
            n,a=arrays['ngspice'];ns,b=arrays['xyce']
            for node in ['generic','generic_tie','generic_wide']:
                reference=a[:,n.index('v('+node+')')]
                candidate=b[:,ns.index('v('+node+')')]
                interpolated=np.interp(a[:,n.index('time')],b[:,ns.index('time')],candidate)
                self.assertLess(float(np.max(np.abs(reference-interpolated))),1e-9)


if __name__=='__main__':unittest.main()
