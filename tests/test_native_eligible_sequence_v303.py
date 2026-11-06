# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import select_native_eligible_sequence_v303 as p
import regenerated_bank_periodic_measure_v67 as timing
import export_proposed_code_rom_v297 as exporter


class NativeEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=[]
        observations=dict(whole_bank_rc_retained=True,terminal_stress=[dict(passed=True)]*1529,
            programming_gates=[dict(passed=True)]*173,controls=[dict(passed=True)]*86)
        for s in p.source.specifications():
            code=s['coarse']*32+s['fine'];corner=p.selector.PVT.index(s['process']+':'+str(s['temperature']))
            delay=500+code*3+corner*.1
            r=dict(observations,**{flag:True for flag in p.source.sparse.NATIVE_FLAGS},
                edge_delays_ps={edge:[delay+k*.01 for k in range(8)] for edge in ('rise','fall')})
            cls.rows.append(dict(spec=s,result=r,error=None))

    def changed(self,code,corner,changes):
        rows=list(self.rows)
        index=next(k for k,r in enumerate(rows) if r['spec']['coarse']*32+r['spec']['fine']==code
            and r['spec']['process']+':'+str(r['spec']['temperature'])==corner)
        rows[index]=dict(rows[index],result=dict(rows[index]['result'],**changes));return rows

    def test_complete_coverage_and_universal_eligibility_preserve_original_rom_contract(self):
        r=p.assess(self.rows);self.assertEqual(len(r['raw_point_records']),7680)
        self.assertEqual(r['eligible_codes'],list(range(512)));self.assertEqual(r['excluded_codes'],[])
        self.assertTrue(r['all_raw_codes_passed']);self.assertTrue(r['common_sequence_found'])
        params=exporter.parameters(r['proposed_common_sequence'])
        self.assertEqual(params['NATIVE_CODE_COUNT'],512);self.assertEqual(params['TABLE_MODEL_ADMITTED'],0)
        self.assertEqual(len(r['proposed_common_sequence']['witnesses']),30)

    def test_actual_timing_function_out_of_epoch_failure_is_retained_but_never_selected(self):
        t=np.arange(0,25000,.5);spec=self.rows[-1]['spec'];period=1e6/410
        def wave(delay):return sum(.9*(np.tanh((t-2100-k*period-delay)/20)-np.tanh((t-2100-(k+.5)*period-delay)/20)) for k in range(8))
        result=timing.timing(t,wave(0),wave(3000),spec)
        self.assertTrue(result['all_input_output_pulses_present']);self.assertFalse(result['unwrapped_native_epoch_passed'])
        result.update(periodic_transport_screen_passed=False,current_clock_interface_screen_passed=False)
        r=p.assess(self.changed(511,'sf:40',result))
        self.assertFalse(r['all_raw_codes_passed']);self.assertTrue(r['common_sequence_found'])
        self.assertEqual(r['excluded_codes'],[dict(code=511,failed_pvt=['sf:40'])])
        self.assertNotIn(511,r['eligible_codes']);self.assertNotIn(511,r['proposed_common_sequence']['codes'])
        original=next(x for x in r['raw_point_records'] if x['code']==511 and x['pvt']=='sf:40')
        self.assertIn('unwrapped_native_epoch_passed',original['failed_original_gates'])
        self.assertNotIn('edges',original)  # Never invent a valid interval for a failed point.

    def test_one_corner_failure_excludes_the_code_at_every_corner_and_preserves_path(self):
        changes=dict(repeated_delay_screen_passed=False,periodic_transport_screen_passed=False,current_clock_interface_screen_passed=False)
        r=p.assess(self.changed(10,'fs:25',changes));self.assertTrue(r['common_sequence_found'])
        self.assertNotIn(10,r['eligible_codes']);self.assertNotIn(10,r['proposed_common_sequence']['codes'])
        self.assertEqual(r['excluded_codes'],[dict(code=10,failed_pvt=['fs:25'])])
        self.assertEqual(len(r['raw_point_records']),7680)

    def test_complete_measured_missing_output_is_not_filled_with_an_interval(self):
        changes=dict(edge_delays_ps=dict(rise=[],fall=[]),all_input_output_pulses_present=False,
            full_swing_pulses_passed=False,unwrapped_native_epoch_passed=False,
            periodic_transport_screen_passed=False,current_clock_interface_screen_passed=False)
        r=p.assess(self.changed(10,'ss:40',changes));self.assertTrue(r['common_sequence_found'])
        point=next(x for x in r['raw_point_records'] if x['code']==10 and x['pvt']=='ss:40')
        self.assertEqual(point['measured_edge_counts'],dict(rise=0,fall=0));self.assertNotIn('edges',point)
        self.assertNotIn(10,r['eligible_codes'])

    def test_missing_error_duplicate_or_nonfinite_records_are_not_treated_as_measured_failures(self):
        with self.assertRaisesRegex(ValueError,'complete measured'):p.assess(self.rows[:-1])
        rows=list(self.rows);rows[0]=dict(rows[0],error='measurement failed')
        with self.assertRaisesRegex(ValueError,'complete measured'):p.assess(rows)
        rows=list(self.rows);rows[-1]=rows[0]
        with self.assertRaisesRegex(ValueError,'unique'):p.assess(rows)
        rows=self.changed(10,'tt:0',dict(edge_delays_ps=dict(rise=[float('nan')]*8,fall=[530]*8)))
        with self.assertRaisesRegex(ValueError,'nonfinite'):p.assess(rows)

    def test_incomplete_observations_wrong_reference_or_missing_gate_is_an_error(self):
        for change in (dict(terminal_stress=[]),dict(programming_gates=[]),dict(controls=[]),
            dict(input_timing_stimulus_passed=False),dict(whole_bank_rc_retained=False),dict(period_screen_passed=None)):
            with self.assertRaisesRegex(ValueError,'Incomplete native'):p.assess(self.changed(10,'tt:0',change))

    def test_no_eligible_path_keeps_every_failed_point_and_never_admits_a_table(self):
        rows=[dict(row,result=dict(row['result'],terminal_screen_passed=False,current_clock_interface_screen_passed=False)) for row in self.rows]
        r=p.assess(rows);self.assertEqual(r['eligible_codes'],[]);self.assertFalse(r['common_sequence_found'])
        self.assertEqual(len(r['excluded_codes']),512);self.assertEqual(len(r['raw_point_records']),7680)
        for flag in ('all_clock_conditions_characterized','bank_configuration_selected','legal_code_table_admitted',
            'updates_qualified','rx_range_qualified','physical_rom_qualified','whole_clock_qualified','electrical_qualification_passed','qualified_phy'):
            self.assertFalse(r[flag])

    def test_incomplete_native_campaign_cannot_create_an_eligibility_receipt(self):
        with patch.object(p.source,'bound',side_effect=ValueError('Actual native prerequisites absent')):
            with self.assertRaises(ValueError):p.verify(Path('/unadmitted-native-campaign'))


if __name__=='__main__':unittest.main()
