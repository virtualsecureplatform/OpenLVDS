# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from copy import deepcopy
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    import klayout.db
except ImportError:
    CAD=False
else:
    CAD=True

@unittest.skipUnless(CAD,'CAD environment required by routed RC qualifier')
class IsolatedJointRcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import qualify_isolated_bank_joint_rc_v255 as q
        cls.q=q;cls.base=q.ROOT/'build/diagnostics/isolated_fine_bank_junctions_v246/100682d1c98a6745'
        cls.top='openlvds_isolated_fine_physical_v239'
        cls.ordinary=(cls.base/'ordinary'/(cls.top+'.lvs.spice')).read_text()
        cls.rows=json.loads((q.geometry.MEASUREMENTS/'summary.json').read_text())['rows']
        cls.ports=q.inventory.native.layout.circuits(q.correction.collapse(cls.ordinary))[cls.top+'_flat'][0]

    def raw(self,negative=False):
        text=self.ordinary.replace('.subckt '+self.top+'_flat ','.subckt '+self.top+' ',1)
        text=text.replace('.ends '+self.top+'_flat','.ends '+self.top,1)
        network='Rtest0 IN __wire0 '+('-1.25' if negative else '1.25')+' $ keep\nRtest1 __wire0 __cap0 2.5\nRtest2 __cap0 __wire1 3.75\nRtest3 __wire1 __wire2 4\nCtest __cap0 VGND 2f\nCend __wire2 VGND 3f\n'
        return text.replace('.ends',network+'.ends',1)

    def test_anchors_follow_graph_order_even_when_plan_dictionary_is_permuted(self):
        g=dict(ports=['IN','OUT','VPWR','VGND']);p=dict(ports={n:dict(rect=[i,0,i+1,1]) for i,n in enumerate(reversed(g['ports']))})
        result=self.q.port_anchors(g,p)
        self.assertEqual(list(result),g['ports'])
        self.assertEqual(result['IN']['x_um'],3.5)
        bad=deepcopy(p);bad['ports'].pop('OUT')
        with self.assertRaisesRegex(ValueError,'public ports differ'):self.q.port_anchors(g,bad)

    def test_unqualified_or_wrong_native_bank_cannot_start_joint_rc(self):
        r=dict(native_routed_gds_passed=True,physical=dict(passed=True,drc_count='0',lvs_passed=True),
               native_parameters=dict(native_mos=1479,native_mims=43,newly_characterized_junction_devices=155,
                  native_parameters_preserved=True,all_native_model_dimensions_preserved=True,all_reference_supplied_junctions_preserved=True),
               final_mask_proof=dict(complete=True),final_native_hierarchy_proof=dict(complete=True))
        state=dict(status='complete',passed=True,qualified_phy=False);self.q.require_physical(state,r)
        failures=[dict(r,final_mask_proof=None)]
        bad=deepcopy(r);bad['physical']['lvs_passed']=False;failures.append(bad)
        bad=deepcopy(r);bad['native_parameters']['native_mos']=1453;failures.append(bad)
        for bad in failures:
            with self.assertRaisesRegex(ValueError,'complete routed isolated'):self.q.require_physical(state,bad)
        with self.assertRaises(ValueError):self.q.require_physical(dict(status='routing'),r)

    def test_extractor_provenance_and_port_order_must_match_exactly(self):
        with tempfile.TemporaryDirectory(dir=self.q.ROOT/'build') as tmp:
            d=Path(tmp);files=[d/n for n in ('gds','manifest','native')]
            for f in files:f.write_text(f.name)
            g,m,n=files;info=dict(passed=True,returncode=0,ports_verified=True,ports=['IN','OUT'],fingerprint='fingerprint',
                gds_sha256=self.q.sha(g),source_sha256=self.q.sha(m),source_scope_sha256=self.q.sha(n))
            self.q.verify_fresh(info,'fingerprint',g,m,n,['IN','OUT'])
            for bad in [dict(info,ports=['OUT','IN']),dict(info,source_scope_sha256='stale'),dict(info,passed=False),dict(info,ports_verified=False)]:
                with self.assertRaisesRegex(ValueError,'source/interface binding'):self.q.verify_fresh(bad,'fingerprint',g,m,n,['IN','OUT'])

    def test_native_fixture_correction_reduction_lvs_and_independent_currents(self):
        # The device extraction is real; this tiny added R/C network is a
        # test fixture and supplies no routed-bank qualification evidence.
        runtime=self.q.mathematics.math_proof()['runtime']
        with tempfile.TemporaryDirectory(dir=self.q.ROOT/'build') as tmp:
            r=self.q.qualify_netlists(Path(tmp)/'fixture',self.raw(),self.ordinary,self.top,self.ports,self.rows,runtime)
            self.assertEqual(r['native_parameters']['native_primitives'],1522)
            self.assertEqual(r['native_parameters']['newly_characterized_junction_devices'],0)
            self.assertEqual(r['all_fine_junctions']['joint_rc']['fine_mos_with_all_measured_junction_fields'],155)
            self.assertTrue(r['independent_terminal_current_witness']['passed'])
            self.assertTrue(r['independent_witness_input']['inline_comments_only_removed'])
            self.assertTrue(r['independent_witness_input']['circuit_tokens_preserved'])
            self.assertIn('$ keep',(Path(tmp)/'fixture/raw.spice').read_text())
            self.assertNotIn('$ keep',(Path(tmp)/'fixture/witness_raw.spice').read_text())
            self.assertTrue(all(p['elementwise_passive_passed'] for p in r['passivity'].values()))
            self.assertGreater(r['reduction']['algebraic_nodes_eliminated'],0)

    def test_negative_passive_or_omitted_rc_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.q.ROOT/'build') as tmp:
            with self.assertRaisesRegex(ValueError,'not passive'):
                self.q.qualify_netlists(Path(tmp)/'negative',self.raw(True),self.ordinary,self.top,self.ports,self.rows,{})
            shorted=self.raw().replace('Rtest3 __wire1 __wire2 4','Rtest3 __wire1 VGND 4')
            with self.assertRaisesRegex(ValueError,'shorts distinct formal ports'):
                self.q.qualify_netlists(Path(tmp)/'shorted',shorted,self.ordinary,self.top,self.ports,self.rows,{})
            raw=self.ordinary.replace('.subckt '+self.top+'_flat ','.subckt '+self.top+' ',1)
            with self.assertRaisesRegex(ValueError,'no passive elements'):
                self.q.qualify_netlists(Path(tmp)/'missing',raw,self.ordinary,self.top,self.ports,self.rows,{})

if __name__=='__main__':unittest.main()
