# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import json
import tempfile
from unittest.mock import patch
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_discharge_isolated_fine_bank_v220 as p


class DischargeFineStageAdmission(unittest.TestCase):
    def rows(self):
        return [dict(spec=s,error=None,result=dict(current_clock_interface_screen_passed=True,
                    edge_delays_ps={edge:[700 if s['fine']==31 else 600 if s['coarse']==1 else 400]*8 for edge in ('rise','fall')})) for s in p.specifications()]

    def test_complete_history_and_both_edge_overlap_are_required(self):
        rows=self.rows();result=p.compare(rows)
        self.assertEqual(len(result),2);self.assertTrue(all(r['component_hypothesis_passed'] for r in result))
        self.assertTrue(all(not r['whole_bank_rc_qualified'] and not r['all_pvt_covered'] and not r['qualified_phy'] for r in result))
        self.assertIsNone(p.compare(rows[:-1]))
        for edge in ('rise','fall'):
            changed=deepcopy(rows);changed[0]['result']['edge_delays_ps'][edge][0]=590
            self.assertFalse(p.compare(changed)[0]['component_hypothesis_passed'])
        changed=deepcopy(rows);changed[0]['result']['current_clock_interface_screen_passed']=False
        self.assertFalse(p.compare(changed)[0]['component_hypothesis_passed'])
        for values in ([],[float('nan')]*8):
            changed=deepcopy(rows);changed[0]['result']['edge_delays_ps']['rise']=values
            self.assertFalse(p.compare(changed)[0]['component_hypothesis_passed'])
        changed=deepcopy(rows);changed[0]['spec']=changed[1]['spec']
        with self.assertRaises(ValueError):p.compare(changed)

    def test_actual_native_transform_and_complete_programming_gate_coverage(self):
        parent=p.ROOT/'build/diagnostics/measured_gang_sparse_v131/58a9364cba76fa27'
        clock=p.ROOT/'build/diagnostics/counter_native_repairs_v183/15c6a8caf6163935'
        if not (parent/'bank.spice').exists() or not (clock/'cells.spice').exists():self.skipTest('requires retained native component artifacts')
        import json
        driver_parent=p.ROOT/'build/diagnostics/discharge_fine_driver_rc_v219/7a09244f3f729a64'
        report=json.loads((driver_parent/'summary.json').read_text())
        bank=(parent/'bank.spice').read_text();cells=(clock/'cells.spice').read_text()+'\n'+'\n'.join((p.ROOT/r['extraction']['netlist']).read_text() for r in report['rows']);previous=json.loads((parent/'manifest.json').read_text())['identity']['observations']
        for v in p.variants():
            with self.subTest(variant=v):
                new=p.transform(bank,cells,v);o=p.observations(new,previous,v);defs=p.native.definitions(new)
                self.assertEqual(len(o['programming_gates']),173)
                self.assertEqual(len(o['devices']),1479 if v['driver']=='p20n16' else 1483)
                units=[w for w in defs[p.TOP][1] if w[0].startswith('Xfine_unit')]
                self.assertEqual(len(units),31*v['fine_copies']);self.assertTrue(all(w[1]=='fine_node' for w in units))
                self.assertEqual([w for w in defs[p.TOP][1] if w[0]=='Xfine_regenerate'],[['Xfine_regenerate','fine_node','OUT','VGND','VPWR',p.BUF]])
        with self.assertRaises(ValueError):p.transform(bank.replace('Xfine_compound selected OUT','Xfine_compound OUT selected'),cells,p.variants()[0])
        with self.assertRaises(ValueError):p.transform(bank,cells,dict(driver='unknown',fine_copies=1))


if __name__=='__main__':unittest.main()
