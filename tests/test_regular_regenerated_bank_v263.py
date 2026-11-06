# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_regular_regenerated_bank_v263 as pilot


class RegularRegeneratorTests(unittest.TestCase):
    def rows(self):
        rows=[]
        for spec in pilot.specifications():
            delay={(0,0):500,(0,31):850,(1,0):700}[spec['coarse'],spec['fine']]
            rows.append(dict(spec=spec,error=None,result=dict(current_clock_interface_screen_passed=True,
                edge_delays_ps={edge:[delay+k*.1 for k in range(8)] for edge in ('rise','fall')})))
        return rows

    def test_zero_first_and_both_duty_endpoints_with_original_native_stimulus(self):
        specs=pilot.specifications()
        self.assertEqual([(s['coarse'],s['fine'],s['duty']) for s in specs],[(0,0,.5),(0,31,.6),(0,31,.4),(1,0,.5)])
        identity=dict(model='native.lib',ports=['IN','OUT','VPWR','VGND'],observations=dict(devices=[],controls=[]))
        for spec in specs:
            self.assertEqual((spec['process'],spec['temperature'],spec['frequency_mhz']),('ss',40,410))
            text=pilot.fixture(Path('/unused'),identity,spec)
            self.assertEqual(text.count('tanh('),16)
            self.assertIn('.tran 2p 25n 0 2p',text)
            self.assertIn('V(XD:restored_b)',text)
            self.assertIn('VDD VDD 0 1.8',text)

    def test_every_gate_eight_edges_and_conservative_overlap_remain_required(self):
        rows=self.rows();self.assertTrue(pilot.compare(rows)['component_hypothesis_passed'])
        self.assertIsNone(pilot.compare(rows[:3]))
        for changed in ('gate','missing','nonfinite','overlap'):
            bad=deepcopy(rows)
            if changed=='gate':bad[0]['result']['current_clock_interface_screen_passed']=False
            if changed=='missing':bad[0]['result']['edge_delays_ps']['rise'].pop()
            if changed=='nonfinite':bad[0]['result']['edge_delays_ps']['rise'][0]=float('nan')
            if changed=='overlap':bad[-1]['result']['edge_delays_ps']['rise'][-1]=900
            self.assertFalse(pilot.compare(bad)['component_hypothesis_passed'])
        with self.assertRaisesRegex(ValueError,'coverage'):pilot.compare(list(reversed(rows)))

    def test_actual_native_bank_pair_has_correct_polarity_supplies_and_preserved_controls(self):
        parent=pilot.ROOT/'build/diagnostics/discharge_isolated_fine_bank_v220/9e4d0f5b90541807'
        if not (parent/'manifest.json').exists():self.skipTest('Native bank artifact unavailable')
        identity=json.loads((parent/'manifest.json').read_text())['identity']
        bank=(parent/'p20n16_c1/bank.spice').read_text();old=identity['observations']['p20n16_c1']
        result,obs,proof=pilot.transform(bank,old)
        body=pilot.native.definitions(result)[pilot.TOP][1]
        stages=[r for r in body if r[0].startswith('Xfine_regenerate')]
        self.assertEqual(stages,[['Xfine_regenerate0','fine_node','restored_b','VGND','VPWR',pilot.MODEL],
                                 ['Xfine_regenerate1','restored_b','OUT','VGND','VPWR',pilot.MODEL]])
        self.assertEqual(len(obs['devices']),1529);self.assertEqual(proof['native_mims'],43)
        self.assertEqual(obs['programming_gates'],old['programming_gates'])
        self.assertEqual(obs['controls'],old['controls'])
        self.assertFalse(proof['qualified_phy'])
        with self.assertRaisesRegex(ValueError,'pin order'):
            pilot.transform(bank.replace('.subckt '+pilot.MODEL+' A Y VGND VPWR',
                                         '.subckt '+pilot.MODEL+' A Y VPWR VGND'),old)


if __name__=='__main__':unittest.main()
