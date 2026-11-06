# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from hashlib import sha256
import json
import re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regular_regenerated_junctions_v280 as p
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/diagnostics/regular_regenerated_junctions_v276/ca85f4dd7ca7a27a'
RAW=BASE/'ordinary/openlvds_regular_regenerated_physical_v273.lvs.spice'
MEASUREMENTS=ROOT/'build/diagnostics/moscap_primitive_junctions_v85/787f8642d60dd868/summary.json'
TOP='openlvds_regular_regenerated_physical_v273_flat'

@unittest.skipUnless(RAW.exists() and MEASUREMENTS.exists(),'Native isolated-bank geometry and extraction required')
class NativeCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=RAW.read_text();cls.rows=json.loads(MEASUREMENTS.read_text())['rows']

    def test_real_correction_preserves_every_noncapacitor_card(self):
        corrected,proof=p.reconstruct(self.source,TOP,self.rows)
        self.assertEqual((proof['identified_capacitor_mos'],proof['corrected_devices'],proof['corrected_fields']),(62,62,124))
        self.assertEqual((proof['native_census']['native_mos'],proof['native_census']['native_mims']),(1529,43))
        changes={r['instance'] for r in proof['corrections']}
        before=p.records(self.source);after=p.records(corrected)
        self.assertEqual(set(before),set(after))
        for name,(a,b) in before.items():
            if name not in changes:
                x,y=after[name];self.assertEqual(self.source[a:b],corrected[x:y])
        # Independently check every one of the 155 fine-device junctions.
        _,devices=p.fine.native.native_leaves(p.collapse(corrected),TOP);lookup={d['name']:d for d in devices}
        library=p.fine.junctions.junction_library(self.rows);count=0
        for section in p.fine.identify(p.collapse(corrected),TOP)['sections']:
            for role in ('capacitor_n','capacitor_p','pass_n','pass_p','clear'):
                d=lookup[section[role]];target=library[p.fine.junctions.geometry_key(d)]['values']
                self.assertEqual({f:p.fine.native.exact_number(d['params'][f]) for f in p.FIELDS},
                                 {f:p.fine.native.exact_number(target[f]) for f in p.FIELDS});count+=1
        self.assertEqual(count,155)
        self.assertFalse(proof['joint_rc_qualified']);self.assertFalse(proof['qualified_phy'])

    def test_correction_is_byte_idempotent_and_preserves_passives(self):
        source=self.source.replace('.ends','Rguard __a __b 1.25 $ retain exactly\nCguard __b VGND 2f $ retain exactly\n.ends',1)
        corrected,proof=p.reconstruct(source,TOP,self.rows)
        self.assertEqual(p.passive_lines(source),p.passive_lines(corrected))
        self.assertEqual(proof['passive_record_count'],2)
        again,repeated=p.reconstruct(corrected,TOP,self.rows)
        self.assertEqual(again,corrected);self.assertEqual(repeated['corrected_devices'],0)

    def test_incomplete_geometry_or_changed_capacitor_topology_is_rejected(self):
        for source,rows in [(self.source,self.rows[:1]),(self.source.replace('w=1.26','w=1.25',1),self.rows)]:
            with self.assertRaises(ValueError):p.reconstruct(source,TOP,rows)

    def test_published_measured_reference_regenerates_and_preserves_original_evidence(self):
        parent=ROOT/'build/diagnostics/regular_regenerated_junction_reference_v279/56daa1af193011cf'
        if not (parent/'summary.json').exists():self.skipTest('Completed measured-reference artifact unavailable')
        report=json.loads((parent/'summary.json').read_text())
        self.assertEqual(json.loads((parent/'state.json').read_text()),dict(status='complete',passed=True,qualified_phy=False))
        self.assertTrue(all(sha256((parent/n).read_bytes()).hexdigest()==h for n,h in report['files'].items()))
        corrected,proof=p.reconstruct(self.source,TOP,self.rows)
        self.assertEqual((parent/'measured_reference.spice').read_text(),corrected)
        self.assertEqual(report['correction'],proof)
        self.assertEqual(report['all_fine_junctions'],dict(fine_mos_with_all_measured_junction_fields=155,capacitor_mos=62,programming_mos=93))
        self.assertTrue(report['original_extraction_preserved']);self.assertTrue(report['correction_byte_idempotent'])
        self.assertEqual(RAW.read_text(),self.source)
        self.assertFalse(p.fine.diagnose(p.collapse(self.source),TOP,self.rows)['per_device_capacitor_junctions_match_geometry'])
        for flag in ('whole_bank_native_lvs_passed','joint_rc_qualified','electrical_qualification_passed','qualified_phy'):
            self.assertFalse(report[flag])

if __name__=='__main__':unittest.main()
