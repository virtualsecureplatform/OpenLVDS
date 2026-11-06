# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from copy import deepcopy
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_isolated_bank_transport_followup_v259 as p

class TransportFollowupTests(unittest.TestCase):
    def write(self,path,state,result):
        (path/'state.json').write_text(json.dumps(state));(path/'summary.json').write_text(json.dumps(result));return path

    def row(self):
        return dict(error=None,result=dict(terminal_stress=[{}]*1479,programming_gates=[{}]*173,terminal_screen_passed=True,
            control_settling_passed=True,whole_bank_rc_retained=True,joint_rc_zero_screen_passed=True,output_slew_domain_passed=True))

    def test_zero_stage_requires_all_actual_native_observations_and_safety(self):
        state=dict(status='complete',cases=1,errors=0,qualified_phy=False);good=dict(rows=[self.row()])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);p.require_screen(self.write(path,state,good),'zero')
            for key,value in [('terminal_stress',[{}]*1453),('programming_gates',[{}]*172),('terminal_screen_passed',False),('output_slew_domain_passed',False)]:
                bad=deepcopy(good);bad['rows'][0]['result'][key]=value
                with self.assertRaises(ValueError):p.require_screen(self.write(path,state,bad),'zero')

    def test_periodic_stage_requires_complete_27_cases_overlap_and_every_clock_gate(self):
        state=dict(status='complete',cases=27,errors=0,qualified_phy=False)
        c=dict(conservative_coarse_overlap_ps=dict(rise=20,fall=25),all_periodic_transport_cases_passed=True,
            all_current_clock_interface_cases_passed=True,complete_native_edge_histories=True,actual_joint_rc_retained=True)
        good=dict(rows=[self.row() for _ in range(27)],comparison=c)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);p.require_screen(self.write(path,state,good),'periodic')
            for key in ('all_periodic_transport_cases_passed','all_current_clock_interface_cases_passed','complete_native_edge_histories','actual_joint_rc_retained'):
                bad=deepcopy(good);bad['comparison'][key]=False
                with self.assertRaises(ValueError):p.require_screen(self.write(path,state,bad),'periodic')
            with self.assertRaises(ValueError):p.require_screen(self.write(path,state,dict(good,rows=good['rows'][:-1])),'periodic')
            bad=deepcopy(good);bad['comparison']['conservative_coarse_overlap_ps']['rise']=-1
            with self.assertRaises(ValueError):p.require_screen(self.write(path,state,bad),'periodic')

    def test_incomplete_rc_or_wrong_context_does_not_start_native_simulation(self):
        for state in [dict(status='qualifying_joint_rc'),dict(status='failed'),dict(status='joint_rc_complete',artifacts={}),
            dict(status='joint_rc_complete',artifacts=dict(joint_rc='build/diagnostics/unguarded_bank_joint_rc_v171/82a3dfbf3d1494ac'))]:
            with self.assertRaises(ValueError):p.ready_rc(state)

if __name__=='__main__':unittest.main()
