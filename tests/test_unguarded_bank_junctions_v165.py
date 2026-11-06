# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unguarded_bank_junctions_v165 as p
import measured_bank_junction_reconstruction_v142 as original
import test_measured_bank_junction_reconstruction_v142 as fixture


class UnguardedBankJunctionTests(unittest.TestCase):
    def test_exact_new_census_preserves_all_other_repair_invariants(self):
        f=fixture.MeasuredBankJunctionReconstructionTests();text=f.bank()
        revised=''.join(l for l in text.splitlines(keepends=True) if not l.startswith(('XextraC9 ','XextraC10 ')))
        corrected,proof=p.reconstruct(revised,'bank',f.measurements(),'b2')
        self.assertEqual(proof['native_census']['native_mos'],1453);self.assertEqual(proof['native_census']['native_mims'],40)
        self.assertEqual(proof['corrected_devices'],62);self.assertEqual(proof['corrected_fields'],248)
        self.assertEqual(p.passive_lines(revised),p.passive_lines(corrected));self.assertEqual(p.signature(revised,'bank'),p.signature(corrected,'bank'))
        again,q=p.reconstruct(corrected,'bank',f.measurements(),'b2');self.assertEqual(again,corrected);self.assertEqual(q['corrected_devices'],0)
        with self.assertRaises(ValueError):original.reconstruct(revised,'bank',f.measurements(),'b2')
        with self.assertRaises(ValueError):p.reconstruct(text,'bank',f.measurements(),'b2')
        self.assertEqual(original.reconstruct(text,'bank',f.measurements(),'b2')[1]['native_census']['native_mims'],42)

    def test_observation_metadata_retargets_only_the_final_output(self):
        import unguarded_bank_variant_v164 as variant
        cell=dict(name='u_fine_compound',model=variant.PAIR,pins=dict(A='selected',Y='OUT'))
        other=dict(name='u_group_compound0',model=variant.PAIR,pins=dict(A='tree0_0',Y='regenerated0'))
        source=dict(graph=dict(top=variant.NEW_TOP,cells=[cell,other],orders={variant.PAIR:['A','Y','VPWR','VGND']}),
                    plan=dict(cells=[cell,other],placements=dict(u_fine_compound=[58.78,33.76],u_group_compound0=[0,0])))
        revised=p.census.metadata(source)
        for key in ('graph','plan'):
            self.assertEqual(source[key]['cells'][0]['model'],variant.PAIR)
            self.assertEqual(revised[key]['cells'][0]['model'],variant.NEW_PAIR)
            self.assertEqual(revised[key]['cells'][1],source[key]['cells'][1])
        self.assertEqual(revised['plan']['placements'],source['plan']['placements'])
        self.assertEqual(revised['graph']['orders'][variant.NEW_PAIR],source['graph']['orders'][variant.PAIR])
        source['plan']['cells']=source['plan']['cells'][1:]
        with self.assertRaises(ValueError):p.census.metadata(source)

    def test_reconstruction_body_retains_frozen_original_checks(self):
        a=Path(original.__file__).read_text().split('def reconstruct',1)[1]
        b=Path(p.__file__).read_text().split('def reconstruct',1)[1]
        self.assertEqual(a,b)


if __name__=='__main__':unittest.main()
