# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_regular_regenerated_physical_v284 as follow


class RegularPairContinuationTests(unittest.TestCase):
    def native(self,parent):
        specs=[dict(coarse=c,fine=f,duty=d) for c,f,d in [(0,0,.5),(0,31,.6),(0,31,.4),(1,0,.5)]]
        tasks=[dict(id=str(k),spec=s) for k,s in enumerate(specs)];rows=[]
        # Metadata fixture only: the production route gate additionally binds
        # the real engine/source/decks and remeasures every complete waveform.
        for task in tasks:
            s=task['spec'];delay=900 if s['fine'] else 700 if s['coarse'] else 500
            result=dict({k:True for k in follow.NATIVE_FLAGS},terminal_stress=[dict(passed=True)]*1529,
                programming_gates=[dict(passed=True)]*173,controls=[dict(passed=True)]*2,
                edge_delays_ps={edge:[delay]*8 for edge in ('rise','fall')})
            rows.append(dict(task=task,spec=s,error=None,result=result))
        identity=dict(version='qualified-regular-p20n16-pair-output-regeneration-native-pilot-v263.1',specs=specs,
            observations=dict(devices=[0]*1529,programming_gates=[0]*173,controls=[0]*2))
        (parent/'manifest.json').write_text(json.dumps(dict(identity=identity,tasks=tasks)))
        (parent/'state.json').write_text(json.dumps(dict(status='complete',cases=4,errors=0,qualified_phy=False)))
        report=dict(rows=rows,comparison=dict(component_hypothesis_passed=True,complete_four_point_native_screen=True,
            conservative_coarse_overlap_ps=dict(rise=200,fall=200)))
        self.save(parent,report);return report

    def save(self,parent,report):
        (parent/'summary.json').write_text(json.dumps(report))

    def test_preliminary_gate_requires_every_original_native_point_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory);report=self.native(parent)
            self.assertEqual(follow.require_pilot(parent),report)
            for flag in follow.NATIVE_FLAGS:
                bad=deepcopy(report);bad['rows'][0]['result'][flag]=False;self.save(parent,bad)
                with self.subTest(flag=flag),self.assertRaisesRegex(ValueError,'native point'):follow.require_pilot(parent)

    def test_incomplete_coverage_or_false_overlap_cannot_advance(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory);report=self.native(parent)
            for fault in ('missing_edge','nonfinite','missing_device','missing_gate','overlap'):
                bad=deepcopy(report);v=bad['rows'][0]['result']
                if fault=='missing_edge':v['edge_delays_ps']['rise'].pop()
                if fault=='nonfinite':v['edge_delays_ps']['fall'][0]=float('nan')
                if fault=='missing_device':v['terminal_stress'].pop()
                if fault=='missing_gate':v['programming_gates'].pop()
                if fault=='overlap':bad['rows'][1]['result']['edge_delays_ps']['rise'][0]=600
                self.save(parent,bad)
                with self.subTest(fault=fault),self.assertRaises(ValueError):follow.require_pilot(parent)
            (parent/'state.json').write_text(json.dumps(dict(status='running',qualified_phy=False)))
            with self.assertRaisesRegex(ValueError,'complete four-point'):follow.require_pilot(parent)

    def test_joint_rc_handoff_requires_zero_inferred_junctions_and_all_proofs(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory);(parent/'state.json').write_text(json.dumps(dict(status='complete',passed=True,qualified_phy=False)))
            report=dict(joint_rc_passed=True,regular_regenerated_bank_joint_rc_qualified=True,
                native_parameters=dict(native_mos=1529,native_mims=43,native_primitives=1572,newly_characterized_junction_devices=0,native_parameters_preserved=True),
                native_topology_verified=True,original_extraction_preserved=True,original_and_corrected_reductions_regenerated=True,
                all_fine_junctions={k:dict(fine_mos_with_all_measured_junction_fields=155) for k in ('reference','joint_rc')},
                passivity={k:dict(elementwise_passive_passed=True) for k in ('original_raw','corrected_raw','corrected_reduced')},
                independent_terminal_current_witness=dict(passed=True))
            self.save(parent,report);self.assertEqual(follow.require_result(parent,'rc'),report)
            for fault in ('inferred','fine','passivity','witness','original'):
                bad=deepcopy(report)
                if fault=='inferred':bad['native_parameters']['newly_characterized_junction_devices']=155
                if fault=='fine':bad['all_fine_junctions']['joint_rc']['fine_mos_with_all_measured_junction_fields']=154
                if fault=='passivity':bad['passivity']['corrected_reduced']['elementwise_passive_passed']=False
                if fault=='witness':bad['independent_terminal_current_witness']['passed']=False
                if fault=='original':bad['original_extraction_preserved']=False
                self.save(parent,bad)
                with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,'stage gate failed'):follow.require_result(parent,'rc')

    def test_actual_immutable_handoffs_match_one_native_placement(self):
        root=follow.ROOT/'build/diagnostics'
        pilot=root/'regular_regenerated_bank_v263/7fa8c46ce9db679e'
        evidence=root/'regular_regenerated_routing_verification_v275/13aea70be0ae4a65'
        geometry=root/'regular_regenerated_junctions_v276/ca85f4dd7ca7a27a'
        reference=root/'regular_regenerated_junction_reference_v279/56daa1af193011cf'
        if not all((p/'manifest.json').exists() for p in (pilot,evidence,geometry,reference)):
            self.skipTest('Native regular-pair physical prerequisites unavailable')
        self.assertTrue(follow.require_inputs(pilot,evidence,geometry,reference))
        with self.assertRaisesRegex(ValueError,'explicit unchanged'):
            follow.require_inputs(root/'balanced_isolated_fine_bank_v201/742b7d3b91c0b3b7',evidence,geometry,reference)
        with self.assertRaisesRegex(ValueError,'invocation changed'):
            follow.owner_mode(dict(InvocationID='new',ActiveState='active',MainPID='123'),'old',True)


if __name__=='__main__':unittest.main()
