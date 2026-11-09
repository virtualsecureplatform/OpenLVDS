# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_fast_entry_damping_300_v1 as p
from run_native_binary_v2 import translate


class DampingPilotTests(unittest.TestCase):
    def test_all_twelve_exact_native_cases_and_fresh_controls(self):
        records=list(p.tasks(p.ROOT/'build/unused-damping-pilot-test'))
        self.assertEqual(len(records),12)
        self.assertEqual([r[0]['id'] for r in records],list(map(str,range(12))))
        for k,(task,text,bank,obs,revision) in enumerate(records[:6]):
            other,reference,other_bank,other_obs,other_revision=records[k+6]
            self.assertTrue(task['centered']);self.assertFalse(other['centered'])
            self.assertEqual((task['kind'],task['spec']),(other['kind'],other['spec']))
            self.assertEqual(bank,other_bank);self.assertEqual(obs,other_obs);self.assertEqual(revision,other_revision)
            self.assertEqual(text.replace(p.entry.SOURCE.numerical_trial.CARD+'\n',''),reference)
            self.assertNotIn('I_BENCH_INPUT_CENTER',text+reference);self.assertNotIn('I_BENCH_CURRENT_CENTER',reference)
            original=(p.PARENT/task['source_case']/'bench.cir').read_text()
            untouched=lambda value:[line for line in value.splitlines() if not line.startswith(('.include ','XD ','XL ','.print tran '))]
            self.assertEqual(untouched(text),untouched(original))
            s=task['spec'];self.assertEqual((s['process'],s['temperature'],s['frequency_mhz'],s['duty'],s['stop_ns']),('ss',40,310,.6,40))
            self.assertIn(s['input_slew_ps'],(20,250))
            for deck in (text,reference):
                _,saved=translate(deck)
                for label,prefix in (('first','XD'),('next','XL')):
                    gates=p.metrology.fixed_gates(obs[label],task['kind'],prefix)
                    self.assertTrue({'v('+g['gate_node'].replace(':','.').lower()+')' for g in gates}<=set(saved))

    def test_complete_variant_verdict_requires_both_entry_extremes_and_fresh_pairs(self):
        rows=[]
        for centered in (True,False):
            for k,(kind,source) in enumerate(p.SETTINGS):
                rows.append(dict(task=dict(id=str(k+(0 if centered else 6)),kind=kind,source_case=source,centered=centered),
                    error=None,result=dict(two_bank_zero_pilot_passed=True)))
        pairs={str(k):dict(passed=True) for k in range(6)}
        self.assertTrue(all(p.verdicts(rows,pairs).values()))
        rows[2]['result']['two_bank_zero_pilot_passed']=False
        self.assertFalse(p.verdicts(rows,pairs)['coarse_shunt']);self.assertTrue(p.verdicts(rows,pairs)['combined'])
        pairs['0']['passed']=False;self.assertFalse(p.verdicts(rows,pairs)['combined'])
        with self.assertRaisesRegex(ValueError,'all twelve'):p.verdicts(rows[:-1],pairs)
        with self.assertRaisesRegex(ValueError,'all twelve'):p.verdicts(rows,{})

    def test_new_fixed_gate_failure_cannot_hide_in_original_numerical_pair(self):
        rows=[dict(error=None,result=dict(fixed_shunt_controls_passed=True)),
              dict(error=None,result=dict(fixed_shunt_controls_passed=False))]
        with patch.object(p.entry.previous,'numerical_pair',return_value=dict(passed=True)):
            result=p.numerical_pair(Path('unused'),rows,0,1)
        self.assertFalse(result['passed']);self.assertFalse(result['all_added_gate_classifications_preserved'])
