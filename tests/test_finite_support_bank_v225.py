# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_finite_support_bank_v225 as p


class NativeInputPrecisionParity(unittest.TestCase):
    def references(self):
        parent=p.ROOT/'build/diagnostics/balanced_isolated_fine_bank_v201/742b7d3b91c0b3b7'
        if not (parent/'0/summary.json').exists():self.skipTest('requires completed full-native P20/N10 endpoints')
        return parent,[json.loads((parent/str(k)/'summary.json').read_text())['result'] for k in (0,1)]

    def test_original_failure_all_histories_and_all_native_peaks_must_be_preserved(self):
        _,refs=self.references()
        for ref in refs:self.assertTrue(p.compare_case(ref,ref)['native_waveform_parity_passed'])
        bad=deepcopy(refs[1]);bad['current_clock_interface_screen_passed']=True
        self.assertFalse(p.compare_case(refs[1],bad)['native_waveform_parity_passed'])
        bad=deepcopy(refs[0]);bad['edge_delays_ps']['rise'][-1]+=1.01
        self.assertFalse(p.compare_case(refs[0],bad)['native_waveform_parity_passed'])
        bad=deepcopy(refs[0]);bad['terminal_stress'][-1]['maximum_terminal_difference_v']=float('nan')
        with self.assertRaises(ValueError):p.compare_case(refs[0],bad)
        bad=deepcopy(refs[0]);bad['terminal_stress'].append(bad['terminal_stress'][0])
        with self.assertRaises(ValueError):p.compare_case(refs[0],bad)
        bad=deepcopy(refs[0]);bad['terminal_stress'][0]['limit_v']+=.01
        self.assertFalse(p.compare_case(refs[0],bad)['native_waveform_parity_passed'])

    def test_only_input_expression_and_provenance_title_change_in_actual_native_fixture(self):
        parent,refs=self.references();i=json.loads((parent/'manifest.json').read_text())['identity']
        for spec in p.specifications():
            before=p.source.fixture(parent,i,spec).splitlines();after=p.fixture(parent,i,spec).splitlines()
            changed=[(a,b) for a,b in zip(before,after) if a!=b]
            self.assertEqual(len(before),len(after));self.assertEqual(len(changed),2)
            self.assertTrue(changed[0][0].startswith('OpenLVDS '));self.assertTrue(changed[1][0].startswith('BIN IN 0 V={'))
            self.assertEqual(changed[1][1].count('time<='),16);self.assertEqual(changed[1][1].count('time>='),16)
            self.assertIn('.options timeint method=gear reltol=1e-4 abstol=1e-12',after)
            self.assertIn('.tran 2p 25n 0 2p',after)
            self.assertEqual(spec['cycles'],8)


if __name__=='__main__':unittest.main()
