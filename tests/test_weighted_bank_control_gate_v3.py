# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import weighted_bank_control_gate_v3 as gate
import dcdl_weighted_direct_v4 as circuit


class RepairedBankControlGateTests(unittest.TestCase):
    def fixture(self,root):
        parent=root/'bias-pilot';parent.mkdir()
        specs=gate.verification.pilot.specifications();tasks=[dict(id=str(n),spec=s) for n,s in enumerate(specs)]
        result=dict(component_pilot_passed=True,control_settling_passed=True,terminal_screen_passed=True,maximum_terminal_difference_v=1.9)
        rows=[dict(task=t,result=deepcopy(result),error=None) for t in tasks]
        m=dict(identity=dict(clock='clock',fine_cells='fine',repair='repair'),tasks=tasks)
        (parent/'state.json').write_text(json.dumps(dict(status='fine_control_pilot_complete',cases=4,errors=0)))
        self.write_rows(parent,rows)
        identity=dict(version=gate.verification.VERSION,parent='bias-pilot',inputs={})
        receipt=root/'build/diagnostics/weighted_fine_control_verification_v4'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        receipt.mkdir(parents=True)
        report=dict(identity=identity,groups=gate.verification.assess(rows),all_declared_raw_waveforms_verified=True)
        (receipt/'summary.json').write_text(json.dumps(report))
        return parent,receipt,m,rows,report

    def write_rows(self,parent,rows):(parent/'summary.json').write_text(json.dumps(dict(rows=rows)))

    def test_exact_repaired_family_and_both_biases_are_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);parent,receipt,m,rows,report=self.fixture(root)
            with patch.object(gate,'ROOT',root),patch.object(gate.verification.pilot,'bound',return_value=m):
                proof=gate.require(receipt,root/'clock',root/'fine',root/'repair')
                self.assertTrue(proof['guarded_profile_passed']);self.assertEqual(proof['repair'],'repair')
                for paths in [('other','fine','repair'),('clock','other','repair'),('clock','fine','other')]:
                    with self.assertRaises(ValueError):gate.require(receipt,*[root/p for p in paths])

    def test_high_data_failure_cannot_be_replaced_by_passing_reference_drivers(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);parent,receipt,m,rows,report=self.fixture(root)
            rows[1]['result'].update(component_pilot_passed=False,control_settling_passed=False)
            self.write_rows(parent,rows);report['groups']=gate.verification.assess(rows)
            (receipt/'summary.json').write_text(json.dumps(report))
            with patch.object(gate,'ROOT',root),patch.object(gate.verification.pilot,'bound',return_value=m):
                with self.assertRaises(ValueError):gate.require(receipt,root/'clock',root/'fine',root/'repair')

    def test_numerical_failure_or_missing_bias_blocks_execution(self):
        for incomplete in [False,True]:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);parent,receipt,m,rows,report=self.fixture(root)
                if incomplete:self.write_rows(parent,rows[:1])
                else:(parent/'state.json').write_text(json.dumps(dict(status='fine_control_pilot_complete',cases=4,errors=1)))
                with patch.object(gate,'ROOT',root),patch.object(gate.verification.pilot,'bound',return_value=m):
                    with self.assertRaises(ValueError):gate.require(receipt,root/'clock',root/'fine',root/'repair')

    def test_original_component_profile_receipt_is_not_repair_admission(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);parent,receipt,m,rows,report=self.fixture(root)
            old=root/'build/diagnostics/weighted_fine_control_verification_v3'/receipt.name;old.mkdir(parents=True)
            (old/'summary.json').write_text(json.dumps(report))
            with patch.object(gate,'ROOT',root),patch.object(gate.verification.pilot,'bound') as bound:
                with self.assertRaises(ValueError):gate.require(old,root/'clock',root/'fine',root/'repair')
                bound.assert_not_called()

    def test_repaired_candidate_changes_no_full_bank_topology_or_coarse_choices(self):
        orders={c['model']:list(c['pins']) for c in circuit.core_instances('guarded')}
        orders[circuit.controls.native.CLOCK_BUFFER]=['VGND','X','VPWR','A']
        orders[circuit.controls.native.MODELS['inv_8']]=['A','VGND','Y','VPWR']
        for bit in range(5):orders[circuit.controls.unit.name(bit)]=['NODE','EN','ENB','VDD','VSS']
        actual=circuit.source('guarded',orders)
        self.assertEqual(actual.replace(circuit.NAME,circuit.previous.NAME),circuit.previous.source('guarded',orders))
        self.assertEqual(actual.count('\nX'),94)
        self.assertEqual(len([c for c in circuit.core_instances('guarded') if c['name'].startswith('turn')]),16)
