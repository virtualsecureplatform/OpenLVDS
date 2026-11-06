# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
try:
    import klayout.db as db
except ImportError:
    db=None
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regular_regenerated_bank_physical_v273 as design

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/diagnostics/isolated_fine_placement_v238/da8cd048ac28c378'
PILOT=ROOT/'build/diagnostics/regular_regenerated_bank_v263/7fa8c46ce9db679e'
REFERENCE=ROOT/'build/diagnostics/isolated_fine_bank_junctions_v246/100682d1c98a6745/reference.spice'


@unittest.skipUnless((BASE/'manifest.json').exists() and (PILOT/'bank.spice').exists() and REFERENCE.exists(),'Native bank evidence required')
class RegularRegeneratedPhysicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads((BASE/'manifest.json').read_text())['identity']
        cls.g=design.graph(cls.before['graph']);cls.bank=(PILOT/'bank.spice').read_text()
        cls.reference=design.reference(cls.g,REFERENCE.read_text())

    def test_exact_native_pair_and_all_other_call_pin_maps_preserved(self):
        old={c['name']:c for c in self.before['graph']['cells']};new={c['name']:c for c in self.g['cells']}
        self.assertEqual(set(old)-set(new),{'u_fine_regenerate'})
        self.assertEqual(set(new)-set(old),{'u_fine_regenerate0','u_fine_regenerate1'})
        for name,c in old.items():
            if name!='u_fine_regenerate':self.assertEqual(new[name],c)
        self.assertTrue(design.compare_component(self.g,self.bank)['exact_component_calls_and_named_pins_verified'])
        self.assertEqual(new['u_fine_regenerate0']['pins'],dict(A='fine_node',Y='restored_b',VGND='VGND',VPWR='VPWR'))
        self.assertEqual(new['u_fine_regenerate1']['pins'],dict(A='restored_b',Y='OUT',VGND='VGND',VPWR='VPWR'))

    def test_changed_programming_and_supply_pins_are_rejected(self):
        for name,pin,node in [('u_fine_unit0','CTRL','fine1'),('u_fine_regenerate1','VPWR','VGND')]:
            bad=deepcopy(self.g);next(c for c in bad['cells'] if c['name']==name)['pins'][pin]=node
            with self.assertRaisesRegex(ValueError,'differs from native'):design.compare_component(bad,self.bank)
        with self.assertRaisesRegex(ValueError,'definition port order'):
            design.reference(self.g,(BASE/'reference.spice').read_text())

    def test_corrected_reference_matches_all_1529_mos_and_43_mim(self):
        p=design.inventory_proof(self.g,self.reference,self.bank)
        self.assertEqual((p['native_mos'],p['native_mims']),(1529,43))
        defs=design.original.old.native.definitions(self.reference)
        self.assertEqual(defs[design.DRIVER][0],['A','Y','VPWR','VGND'])
        for model,order in self.g['orders'].items():self.assertEqual(defs[model][0],order)

    def test_real_master_placement_preserves_coarse_mux_and_complete_tapped_rows(self):
        plan=design.placement(self.before['plan'],self.g,self.before['records'])
        self.assertEqual(plan['functional_instances'],181);self.assertEqual(len(plan['cells']),353)
        self.assertEqual(len(plan['tapped_groups']),43)
        dx=design.floor.q(52*design.floor.SITE)
        shifted={f'u_fine_unit{k}' for k in range(31)}
        for group in self.before['plan']['tapped_groups']:
            if group['name'].startswith('fine'):shifted.update(group['cells'])
        for name,xy in self.before['plan']['placements'].items():
            if name=='u_fine_regenerate':continue
            expected=[design.floor.q(xy[0]+dx),xy[1]] if name in shifted else xy
            self.assertEqual(plan['placements'][name],expected,name)
        self.assertEqual(plan['ports']['OUT']['layer'],'met4')
        self.assertEqual({r['net'] for r in plan['fixed_routes']},{'fine_node','VPWR','VGND'})
        self.assertFalse(plan['routed']);self.assertFalse(plan['whole_bank_lvs_passed'])

    def test_actual_completed_placement_has_all_output_hashes_and_scoped_gates(self):
        from hashlib import sha256
        parent=ROOT/'build/diagnostics/regular_regenerated_placement_v272/82dc7493ef40f70d'
        if not (parent/'summary.json').exists():self.skipTest('Completed native placement unavailable')
        report=json.loads((parent/'summary.json').read_text())
        self.assertEqual(json.loads((parent/'state.json').read_text()),dict(status='complete',passed=True,qualified_phy=False))
        self.assertTrue(report['placement_feasibility_passed']);self.assertIsNone(report['error'])
        self.assertEqual(report['placement']['total_instances'],353)
        self.assertEqual(report['placement']['tapped_rows'],43)
        self.assertEqual(report['placement_geometry']['drc_count'],'0')
        self.assertTrue(all(sha256((parent/n).read_bytes()).hexdigest()==h for n,h in report['files'].items()))
        for flag in ('routed','whole_bank_lvs_passed','joint_rc_extracted','timing_candidate_admitted','electrical_qualification_passed','qualified_phy'):
            self.assertIs(report[flag],False,flag)

    @unittest.skipUnless(db is not None,'KLayout required for actual stored-metal audit')
    def test_actual_gds_buses_and_m4_output_contact_reject_wrong_named_rail(self):
        import build_tg_bank_floorplan_v49 as assembly
        parent=ROOT/'build/diagnostics/regular_regenerated_placement_v272/82dc7493ef40f70d'
        if not (parent/'summary.json').exists():self.skipTest('Completed native placement unavailable')
        identity=json.loads((parent/'manifest.json').read_text())['identity'];g=identity['graph'];plan=identity['plan'];records=identity['records']
        file=parent/(g['top']+'.gds');audit=design.fixed_bus_audit(file,g,plan,records)
        self.assertEqual(set(audit),{'fine_node','VPWR','VGND'})
        self.assertTrue(all(row['required_native_rails_connected']==31 for row in audit.values()))
        bad=deepcopy(plan);next(c for c in bad['cells'] if c['name']=='u_fine_unit0')['pins']['A']='wrong_net'
        with self.assertRaisesRegex(ValueError,'different named terminal'):design.fixed_bus_audit(file,g,bad,records)
        lib=db.Layout();lib.read(str(file));top=lib.cell(g['top']);metal=assembly.audit.region(lib,top,(71,20))
        contact=db.Region(db.Box(*[round(v/lib.dbu) for v in plan['ports']['OUT']['rect']]))
        connected=metal.interacting(contact).merged();self.assertEqual(connected.count(),1)
        bx,by=plan['placements']['u_fine_regenerate1']
        for pin in ('A','Y'):
            rect=records[design.DRIVER]['pins'][pin]['shapes'][0][1]
            shape=db.Region(db.Box(*[round(v/lib.dbu) for v in rect]).transformed(db.Trans(round(bx/lib.dbu),round(by/lib.dbu))))
            if pin=='Y':self.assertTrue((shape-connected).is_empty())
            else:self.assertTrue((shape&connected).is_empty())


if __name__=='__main__':unittest.main()
