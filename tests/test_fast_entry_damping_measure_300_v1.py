# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
import tempfile
from copy import deepcopy
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import fast_entry_damping_measure_300_v1 as p
import fast_entry_damping_fixture_300_v1 as fixture


class FixedShuntControlTests(unittest.TestCase):
    def observations(self,kind):
        parent=p.architecture.source.ROOT/'build/diagnostics/tg2_entry_domain_pilot_300_v1/b98f2003774d19d6'
        folder=parent/'2';original=(folder/'bench.cir').read_text();library=(parent/'bank.spice').read_text()
        obs=json.loads((folder/'observations.json').read_text())
        return fixture.fixture(original,library,obs,kind,Path('new-bank.spice'))[2]

    def test_every_actual_fixed_shunt_gate_is_mapped_and_checked_from_dc(self):
        obs=self.observations('combined')
        gates=[]
        for label,prefix in (('first','XD'),('next','XL')):
            unit=p.fixed_gates(obs[label],'combined',prefix)
            self.assertEqual(len(unit),48);self.assertEqual(sum(g['target_v']==1.8 for g in unit),16)
            gates+=unit
        values={g['gate_node']:np.full(3,g['target_v']) for g in gates}
        original=p.check_fixed(values.__getitem__,gates);independent=p.check_fixed(values.__getitem__,gates,independent=True)
        self.assertEqual(original,independent);self.assertTrue(all(g['passed'] for g in original))
        # A DC-only violation must not be hidden by the usual settling mask.
        values[gates[0]['gate_node']][0]+=.181
        original=p.check_fixed(values.__getitem__,gates);independent=p.check_fixed(values.__getitem__,gates,independent=True)
        self.assertEqual(original,independent);self.assertFalse(original[0]['passed'])
        values[gates[0]['gate_node']][0]=float('nan')
        with self.assertRaisesRegex(ValueError,'Invalid'):p.check_fixed(values.__getitem__,gates)

    def test_missing_shunt_and_wrong_intervention_rejected(self):
        obs=self.observations('coarse_shunt')['first']
        with self.assertRaisesRegex(ValueError,'Unexpected shunt'):p.fixed_gates(obs,'decode_drive2','XD')
        obs['devices']=[d for d in obs['devices'] if ':Xtail_load:Xdamp:' not in d['name']]
        with self.assertRaisesRegex(ValueError,'map changed'):p.fixed_gates(obs,'coarse_shunt','XD')
        obs=self.observations('decode_drive2')
        self.assertEqual(p.fixed_gates(obs['first'],'decode_drive2','XD'),[])


    def test_fixed_gate_dc_failure_overrides_otherwise_passing_bank_result(self):
        observations=self.observations('combined');gates={}
        for label,prefix in (('first','XD'),('next','XL')):
            gates[label]=p.fixed_gates(observations[label],'combined',prefix)
        names=['time']+[g['gate_node'] for rows in gates.values() for g in rows]
        values=[np.array([0,2e-9,40e-9])]+[np.full(3,g['target_v']) for rows in gates.values() for g in rows]
        values[1][0]+=.181
        data=np.column_stack(values)
        columns=['time']+['v('+n.replace(':','.').lower()+')' for n in names[1:]]
        header=('Title: fixed-gate reader fixture\nFlags: real\n'
            f'No. Variables: {len(columns)}\nNo. Points: 3\nVariables:\n'
            +''.join(f'\t{k}\t{n}\t'+('time' if k==0 else 'voltage')+'\n' for k,n in enumerate(columns))+'Binary:\n')
        base=dict(banks={label:dict(bank_screen_passed=True) for label in gates},two_bank_zero_pilot_passed=True)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
            # The established timing/terminal reader is tested separately;
            # exercise this wrapper's real binary reader and verdict override.
            with patch.object(p.previous,'measure',side_effect=lambda *a,**kw:deepcopy(base)):
                original=p.measure(folder,observations,dict(fast_entry_intervention='combined'))
                independent=p.measure(folder,observations,dict(fast_entry_intervention='combined'),independent_reader=True)
            self.assertEqual(original,independent)
            self.assertFalse(original['two_bank_zero_pilot_passed'])
            self.assertFalse(original['banks']['first']['bank_screen_passed'])
            self.assertTrue(original['banks']['next']['bank_screen_passed'])
