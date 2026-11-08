# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import hashlib
from unittest.mock import patch
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcc_chain_300_v2 as p
import test_dcc_chain_measure_300_v1 as fixtures


class CombinedControllerTests(unittest.TestCase):
    def test_actual_material_pair_changes_only_include_paths(self):
        out=p.ROOT/'build/unused-combined-controller-test'
        decks=[]
        for k in ('0','1'):
            original=(p.MATERIAL/k/'bench.cir').read_text();text=p.fixture(original,out,k=='0');decks.append(text)
            for name in ('bank.spice','dcc.spice'):
                self.assertIn(f'.include "{out/name}"',text)
                text=text.replace(f'.include "{out/name}"',f'.include "{p.MATERIAL/name}"')
            if k=='0':text=text.replace(p.trial.CARD+'\n','',1)
            self.assertEqual(text,original)
        self.assertEqual(decks[0].replace(p.trial.CARD+'\n','').replace(p.materials.chain.SOURCE.numerical_trial.CARD+'\n',''),decks[1])

    def test_binary_pair_preserves_internal_failure_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);rows=[]
            for k in range(2):
                folder=out/str(k);folder.mkdir();obs,s=fixtures.CombinedBinaryTests().fixture(folder)
                names,w=p.validate(folder/'bench.raw',set(),40e-9)
                values={n:np.array(w[:,j]) for j,n in enumerate(names)}
                for dcc in range(2):
                    for n in ('a','b'):values[f'v(xdc{dcc}.{n})']=values['v(in)']
                del w
                names=list(values);data=np.column_stack(list(values.values()))
                header=('Title: synthetic pair reader fixture\nFlags: real\n'
                    f'No. Variables: {len(names)}\nNo. Points: {len(data)}\nVariables:\n'
                    +''.join(f'\t{j}\t{n}\t'+('time' if j==0 else 'voltage')+'\n' for j,n in enumerate(names))+'Binary:\n')
                (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
                # Pulse crossing and classification comparison are tested here;
                # actual pulse hold metrology has its own full binary tests.
                result=p.metrology.previous.measure(folder,obs,s)
                result['dcc']['0']['pulse_generators']={'a':dict(passed=True)}
                rows.append(dict(task=dict(id=str(k),centered=k==0,spec=s),error=None,result=result))
            pair=p.numerical_pair(out,rows)
            self.assertTrue(pair['passed']);self.assertTrue(p.pilot_passed(rows,pair))
            rows[1]['result']['dcc']['0']['pulse_generators']['a']['passed']=False
            self.assertFalse(p.numerical_pair(out,rows)['passed'])
            rows[1]['result']['combined_loading_transport_passed']=False
            self.assertFalse(p.pilot_passed(rows,pair))
            rows[1]['error']='native failure'
            self.assertFalse(p.numerical_pair(out,rows)['passed'])
            with self.assertRaises(ValueError):p.pilot_passed(rows[:1],pair)


class ConvergenceReferenceGateTests(unittest.TestCase):
    def receipt(self,root,*,passed=True):
        trial=root/'trial';(trial/'0').mkdir(parents=True)
        for n in ('manifest.json','state.json','summary.json','bank.spice'):
            (trial/n).write_text('synthetic gate fixture\n')
        folder=trial/'0'
        for n in ('bench.raw','bench.cir','bench.ngspice.cir','ngspice.log','observations.json'):
            (folder/n).write_text('synthetic gate witness, not a simulation\n')
        row=dict(error=None,result={},parity=dict(passed=True),files={x.name:p.sha(x) for x in folder.iterdir()})
        p.atomic(folder/'summary.json',row)
        inputs={str(x.relative_to(root)):p.sha(x) for x in trial.rglob('*') if x.is_file()}
        identity=dict(version=p.reference.VERSION,parent=str(trial.relative_to(root)),inputs=inputs)
        proof=root/'build/diagnostics'/p.reference.CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        proof.mkdir(parents=True)
        p.atomic(proof/'manifest.json',dict(identity=identity,qualified_phy=False))
        p.atomic(proof/'state.json',dict(status='complete',cases=1,qualified_phy=False))
        p.atomic(proof/'summary.json',dict(all_original_metrics_reproduced=True,independent_metrics_reproduced=True,
            numerical_comparison_reproduced=True,numerical_origin_passed_for_reference_case=passed,
            parity=dict(passed=passed),parameters_changed=False,combined_circuit_admitted=False,qualified_phy=False))
        return trial,proof

    def test_pending_and_failed_reference_cannot_prepare_combined_run(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p.materials,'check',side_effect=AssertionError('must gate before materials')):
            with self.assertRaisesRegex(ValueError,'pending'):p.prepare(Path(tmp)/'pending')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trial,proof=self.receipt(root,passed=False)
            with patch.object(p,'ROOT',root),patch.object(p,'TRIAL',trial),patch.object(p.materials,'check',side_effect=AssertionError('must gate')):
                with self.assertRaisesRegex(ValueError,'passing independently'):p.prepare(proof)

    def test_complete_reference_binding_and_modified_witness_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trial,proof=self.receipt(root)
            with patch.object(p,'ROOT',root),patch.object(p,'TRIAL',trial):
                evidence=p.require_reference(proof)
                self.assertIn(str((trial/'0/bench.raw').relative_to(root)),evidence)
                self.assertIn(str((proof/'summary.json').relative_to(root)),evidence)
                (trial/'0/bench.raw').write_text('changed native witness\n')
                with self.assertRaisesRegex(ValueError,'witness changed'):p.require_reference(proof)

    def test_reference_deck_cannot_receive_intervention_accidentally(self):
        text=(p.MATERIAL/'1/bench.cir').read_text()
        with self.assertRaisesRegex(ValueError,'origin does not match'):p.fixture(text,p.ROOT/'build/unused',True)
