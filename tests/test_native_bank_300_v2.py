# SPDX-License-Identifier: GPL-3.0-only
import json,sys,unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_bank_300_v2 as p
class SingleDriverPilotTests(unittest.TestCase):
    def base(self):
        row=json.loads((p.PARENTS['restored'][1]/'0/summary.json').read_text())
        return row['result'],dict(row['spec'],frequency_mhz=310,stop_ns=40)
    def test_fastest_band_budget_replaces_legacy_quarter_gate(self):
        r,s=self.base();out=p.contract(r,s)
        self.assertAlmostEqual(out['zero_code_fast_quarter_headroom_ps'],806.4516129032259-max(v for a in r['edge_delays_ps'].values() for v in a))
        self.assertEqual(r['zero_code_fast_quarter_headroom_ps'],json.loads((p.PARENTS['restored'][1]/'0/summary.json').read_text())['result']['zero_code_fast_quarter_headroom_ps'])
        self.assertFalse(out['qualified_phy'])
    def test_nominal_quarter_is_not_sufficient_for_fast_boundary(self):
        r,s=self.base();r=deepcopy(r);r['edge_delays_ps']={e:[820.]*8 for e in ('rise','fall')}
        self.assertFalse(p.contract(r,s)['zero_code_quarter_passed'])
    def test_no_legacy_frequency_or_missing_event_can_qualify(self):
        r,s=self.base()
        with self.assertRaises(ValueError):p.contract(r,dict(s,frequency_mhz=410))
        r=deepcopy(r);r['edge_delays_ps']['rise'].pop()
        self.assertFalse(p.contract(r,s)['zero_code_quarter_passed'])
    def test_other_failed_gates_are_never_repaired_by_frequency_change(self):
        for key in ('terminal_screen_passed','control_settling_passed','period_screen_passed','repeated_delay_screen_passed'):
            r,s=self.base();r[key]=False
            self.assertFalse(p.contract(r,s)['current_clock_interface_screen_passed'])
    def test_fresh_fixtures_include_longest_clock_window_and_all_events(self):
        for kind,(producer,parent) in p.PARENTS.items():
            old=json.loads((parent/'manifest.json').read_text())['identity'];i=dict(kind=kind,source_identity=old,macro_top='openlvds_test_300')
            for spec,centered in p.specifications(kind):
                text=p.fixture(p.ROOT/'build/unused-native-300',i,spec,centered)
                self.assertIn('.tran 2p 40n 0 2p',text)
                self.assertEqual(text.count('tanh((time-'),16)
                self.assertEqual(text.count(p.numerical.CARD),int(centered))
                self.assertIn('.lib "'+old['model']+'" ss',text)
                self.assertEqual(text.count('openlvds_test_300'),1)
