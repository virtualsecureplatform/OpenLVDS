# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_measured_balanced_joint_periodic_v154 as p


class JointPeriodicTests(unittest.TestCase):
    def specs(self):return p.specifications(p.native.spec('b2'))

    def rows(self):
        return [dict(spec=s,error=None,result=dict(periodic_transport_screen_passed=True,current_clock_interface_screen_passed=True,whole_bank_rc_retained=True)) for s in self.specs()]

    def test_complete_authorized_frequency_duty_code_matrix_and_full_tail(self):
        for profile in ('b2','b3'):
            specs=p.specifications(p.native.spec(profile))
            self.assertEqual(len(specs),27)
            self.assertEqual({(s['coarse'],s['fine'],s['frequency_mhz'],s['duty']) for s in specs},
                             {(c,f,m,d) for c,f in ((0,0),(0,31),(1,0)) for m in (390,400,410) for d in (.4,.5,.6)})
            for s in specs:
                self.assertEqual((s['profile'],s['process'],s['temperature'],s['input_slew_ps'],s['load_ff']),(profile,'ss',40,100,20))
                self.assertGreater(s['stop_ns'],2.1+(s['cycles']-1+s['duty']+1)*1000/s['frequency_mhz'])

    def test_periodic_fixture_changes_only_title_input_wave_and_stop_time(self):
        ports=['IN','OUT',*[f'S{k}' for k in range(4)],*[f'E{k}' for k in range(31)],'VPWR','VGND']
        i=dict(top='bank',ports=ports,model='/model.lib',observations=dict(devices=[dict(terminals=['XD:drain.t0','XD:gate.t1','0','VDD'])],controls=[dict(node='XD:control.t2',control='fine0')]))
        for s in self.specs():
            original=p.native.fixture(Path('/fixture'),dict(i,spec=s)).splitlines()
            actual=p.fixture(Path('/fixture'),i,s).splitlines()
            keep=lambda rows:[r for r in rows[1:] if not r.startswith(('BIN IN 0 V=','.tran '))]
            self.assertEqual(keep(actual),keep(original));self.assertEqual(actual[0],'OpenLVDS '+p.VERSION)
            self.assertIn('.tran 2p 25n 0 2p',actual)
            wave=next(r for r in actual if r.startswith('BIN IN 0 V='))
            self.assertEqual(wave.count('tanh('),16)
            for node in ('XD:drain.t0','XD:gate.t1','XD:control.t2'):
                self.assertIn('V('+node+')',actual[-2])

    def test_aggregate_refuses_incomplete_duplicate_relaxed_or_failed_matrix(self):
        rows=self.rows();specs=self.specs();r=p.compare(rows,specs)
        self.assertTrue(r['all_current_clock_interface_cases_passed']);self.assertFalse(r['qualified_phy']);self.assertFalse(r['all_pvt_covered'])
        self.assertIsNone(p.compare(rows[:-1],specs))
        for key in ('periodic_transport_screen_passed','current_clock_interface_screen_passed','whole_bank_rc_retained'):
            changed=deepcopy(rows);changed[0]['result'][key]=False
            result=p.compare(changed,specs)
            self.assertFalse(result['all_periodic_transport_cases_passed'] if key=='periodic_transport_screen_passed' else result['all_current_clock_interface_cases_passed'])
        changed=deepcopy(rows);changed[0]['error']='missing pulse';self.assertIsNone(p.compare(changed,specs))
        changed=deepcopy(rows);changed[0]['spec']=changed[1]['spec']
        with self.assertRaises(ValueError):p.compare(changed,specs)
        changed=deepcopy(rows);relaxed=deepcopy(specs);relaxed[0]['duty']=.7;changed[0]['spec']=relaxed[0]
        with self.assertRaises(ValueError):p.compare(changed,relaxed)


if __name__=='__main__':unittest.main()
