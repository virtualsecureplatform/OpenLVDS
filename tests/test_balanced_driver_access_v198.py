# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json,re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import balanced_driver_access_v198 as p


class NativeEndDrainAccess(unittest.TestCase):
    def test_real_contact_is_required_for_unlabelled_end_connection(self):
        root=Path(__file__).resolve().parents[1]/'build/diagnostics/balanced_driver_pcells_v195/508ff6e991c53541'
        if not (root/'summary.json').exists():self.skipTest('requires retained native primitive geometry')
        rows=json.loads((root/'summary.json').read_text())['rows']
        for row in rows:
            folder=root/row['top'];mag=(folder/(row['top']+'.mag')).read_text();spice=(folder/(row['top']+'.lvs.spice')).read_text()
            accesses,w=p.complete_accesses(row,mag,spice);self.assertEqual(accesses[-1]['name'],'D_end');self.assertTrue(w['native_contact_and_viali_verified']);self.assertFalse(w['ideal_net_alias_added'])
            self.assertEqual(len(w['unlabelled_native_drain_nodes']),1)
            missing=re.sub(r'(?s)<< viali >>.*?(?=<<)', '<< viali >>\n',mag)
            with self.subTest(model=row['top']),self.assertRaises(ValueError):p.complete_accesses(row,missing,spice)
            bad=deepcopy(row);bad['geometry']['bbox'][2]+=.005
            with self.assertRaises(ValueError):p.complete_accesses(bad,mag,spice)


if __name__=='__main__':unittest.main()
