# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_strong_counter_clock_matrix_v264 as matrix
import run_strong_counter_clock_followup_v265 as follow


def result():
    return dict({k:True for k in matrix.FLAGS},terminal_stress=[dict(passed=True)]*matrix.source.NATIVE_MOS,
                minimum_clock_low_voltage_margin_v=.08)


def rows(specs):
    return [dict(task=dict(id=str(k),spec=s),result=result(),error=None) for k,s in enumerate(specs)]


class StrongCounterMatrixTests(unittest.TestCase):
    def test_complete_clock_cartesian_product_and_exact_pilot_reuse(self):
        specs=matrix.specifications()
        actual={(s['process'],s['temperature'],s['mhz'],s['duty'],s['stop_level']) for s in specs}
        expected={(p,t,f,d,l) for p in ('tt','ff','ss','fs','sf') for t in (0,25,40)
                  for f in (390,400,410) for d in (.4,.5,.6) for l in (0,1)}
        self.assertEqual(len(specs),270);self.assertEqual(actual,expected)
        pilot=matrix.source.specifications()
        self.assertTrue(all(s in specs for s in pilot))
        self.assertEqual(len([s for s in specs if s not in pilot]),258)
        self.assertTrue(matrix.assess(rows(specs),specs)['counter_clock_matrix_passed'])

    def test_every_native_gate_terminal_and_clock_low_margin_is_required(self):
        for flag in matrix.FLAGS:
            value=result();value[flag]=False;self.assertFalse(matrix.point_passed(value),flag)
        for margin in (-.01,float('nan'),float('inf'),None):
            value=result();value['minimum_clock_low_voltage_margin_v']=margin
            self.assertFalse(matrix.point_passed(value))
        value=result();value['terminal_stress']=value['terminal_stress'][:-1]
        self.assertFalse(matrix.point_passed(value))
        value=result();value['terminal_stress'][0]=dict(passed=False)
        self.assertFalse(matrix.point_passed(value))

    def test_missing_duplicate_or_failed_condition_cannot_admit_matrix(self):
        specs=matrix.specifications();rs=rows(specs)
        self.assertIsNone(matrix.assess(rs[:-1],specs))
        rs[-1]['task']['spec']=rs[0]['task']['spec']
        with self.assertRaisesRegex(ValueError,'unique 270-case'):matrix.assess(rs,specs)
        rs=rows(specs);rs[-1]['result']['phase_arming_passed']=False
        self.assertFalse(matrix.assess(rs,specs)['counter_clock_matrix_passed'])

    def test_original_full_fixture_and_all_three_frequency_stopped_clocks(self):
        out=Path('/fixture')
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            for mhz in (390,400,410):
                for duty in (.4,.5,.6):
                    for level in (0,1):
                        spec=dict(matrix.source.specifications()[0],mhz=mhz,duty=duty,stop_level=level)
                        text=matrix.fixture(out,spec,[])
                        _,rest=text.split('\n',1)
                        self.assertEqual(rest,matrix.source.fixture(out,spec,[]).split('\n',1)[1])
                        self.assertIn('.tran 1p 26n 0 1p',text)
                        self.assertIn('VDD VDD 0 1.8',text)
                        # The seventh falling edge, if present, precedes REQUEST clear.
                        self.assertLess(2+(6+duty)*1000/mhz+.1,20.99)
                        self.assertIn('.options timeint method=gear reltol=1e-4 abstol=1e-12',text)

    def test_consumption_requires_complete_passing_twelve_case_pilot(self):
        rs=rows(matrix.source.specifications());manifest=dict(tasks=[r['task'] for r in rs])
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory)
            (parent/'state.json').write_text(json.dumps(dict(status='complete',cases=12,errors=0,qualified_phy=False)))
            report=dict(rows=rs,comparison=matrix.source.assess(rs))
            (parent/'summary.json').write_text(json.dumps(report))
            self.assertEqual(matrix.require_pilot(parent,manifest),rs)
            report['rows'][0]['result']['terminal_stress']=[]
            (parent/'summary.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'twelve complete passing'):matrix.require_pilot(parent,manifest)


class StrongCounterFollowupTests(unittest.TestCase):
    def write(self,path,value):
        path.write_text(json.dumps(value))

    def test_completed_matrix_handoff_rechecks_rows_coverage_and_original_gates(self):
        specs=matrix.specifications();rs=rows(specs)
        report=dict(rows=rs[12:],inherited_rows=rs[:12],comparison=matrix.assess(rs,specs))
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            self.write(out/'state.json',dict(status='complete',cases=270,consumed_cases=12,errors=0,qualified_phy=False))
            self.write(out/'summary.json',report);self.assertEqual(follow.require_matrix(out),report)
            report['rows'][0]['result']['phase_arming_passed']=False
            self.write(out/'summary.json',report)
            with self.assertRaisesRegex(ValueError,'original timing'):follow.require_matrix(out)
            report['rows'][0]['result']['phase_arming_passed']=True
            report['rows'][0]['task']['spec']=report['rows'][1]['task']['spec']
            self.write(out/'summary.json',report)
            with self.assertRaisesRegex(ValueError,'unique full matrix'):follow.require_matrix(out)

    def test_pilot_handoff_rejects_incomplete_wrong_context_or_changed_rc(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(follow,'ROOT',Path(directory)):
            relative='build/diagnostics/fast_clear_counter_shared_rc_v269/'+'a'*16
            pilot=Path(directory)/relative;pilot.mkdir(parents=True)
            state=dict(status='fast_clear_counter_pilot_complete',artifacts=dict(transient=relative,rc='expected_rc'))
            self.write(pilot/'state.json',dict(status='complete',cases=12,errors=0,qualified_phy=False))
            self.write(pilot/'summary.json',dict(rows=rows(matrix.source.specifications()),comparison=dict(actual_shared_counter_timing_pilot_passed=True)))
            self.write(pilot/'manifest.json',dict(identity=dict(parent='expected_rc')))
            self.assertEqual(follow.ready_pilot(state),pilot)
            self.write(pilot/'manifest.json',dict(identity=dict(parent='other_rc')))
            with self.assertRaisesRegex(ValueError,'another shared-RC'):follow.ready_pilot(state)
            state['status']='running_transient'
            with self.assertRaisesRegex(ValueError,'completed native'):follow.ready_pilot(state)
            state['status']='fast_clear_counter_pilot_complete';state['artifacts']['transient']='build/diagnostics/other/'+'a'*16
            with self.assertRaisesRegex(ValueError,'explicit strong-counter'):follow.ready_pilot(state)

    def test_changed_owner_is_rejected_even_with_completed_receipt(self):
        with self.assertRaisesRegex(ValueError,'invocation changed'):
            follow.source.owner_mode(dict(InvocationID='new',ActiveState='active',MainPID='123'),'old',True)


if __name__=='__main__':unittest.main()
