# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import static_phase_clock_release_v2 as circuit
import probe_static_phase_clock_release_v2 as pilot
import verify_static_phase_clock_release_v2 as verification
import test_buffered_request_phase_release_v2 as previous
from native_binary_raw_v2 import validate


class StaticPhaseReleaseTests(unittest.TestCase):
    def test_verification_requires_every_declared_profile_and_retains_failed_cases(self):
        result=dict(counter_feasibility_passed=True,terminal_stress=[dict(max_terminal_difference_v=1.9)],
                    margin_to_next_half_phase_ps=dict(prepare=200,public_release=400))
        rows=[dict(task=dict(spec=spec),result=result,error=None) for spec in pilot.specifications()]
        self.assertTrue(all(g['source_counter_feasibility_passed'] for g in verification.assess(rows)))
        with self.assertRaisesRegex(ValueError,'Incomplete'):verification.assess(rows[:-1])
        rows[0]=dict(rows[0],result=None,error='Alternating phase-state event count')
        groups=verification.assess(rows)
        self.assertFalse(groups[0]['source_counter_feasibility_passed'])
        self.assertTrue(groups[1]['source_counter_feasibility_passed'])
        self.assertEqual(groups[0]['measurement_errors'],['Alternating phase-state event count'])

    def test_storage_uses_only_actual_macro_interfaces_with_common_request_reset(self):
        c=circuit.components
        rc={c.MODELS['nand2_'+str(n)]:dict(info=dict(ports=['A','B','Y','VGND','VPWR'])) for n in [4,8]}
        rc[c.CLOCK_BUFFER]=dict(info=dict(ports=['A','X','VGND','VPWR']))
        rc[circuit.NAND2B]=dict(info=dict(ports=['A_N','B','Y','VPWR','VGND']))
        for drive in [4,8]:
            text=circuit.source(rc,drive)
            self.assertEqual(text.count(circuit.NAND2B),3)
            self.assertNotIn('dfrtp',text);self.assertNotIn('XGUARD',text)
            self.assertEqual(len([r for r in text.splitlines() if r.startswith('X')]),19)
            self.assertIn('Xlow0_set CLK request_i low0_sn',text)
            self.assertIn('Xhigh1_set low0 CLK high1_sn',text)
            self.assertIn('Xrelease_q release_sn release_qb RESET_N VGND VPWR '+c.MODELS['nand2_8'],text)
            self.assertEqual(len([r for r in text.splitlines() if '_b ' in r and 'request_i' in r]),6)

    def raw(self,folder,spec,low1_ps=6200,stuck=False):
        previous.BufferedRequestPhaseReleaseTests().raw(folder,spec)
        names,w=validate(folder/'bench.raw',set(),26e-9);t=w[:,names.index('time')]*1e12
        low0=np.where(((t>=4100)&(t<21100))|((t>=23400)&(spec['stop_level']==0)),1.8,0)
        high1=np.where((t>=4700)&(t<21150),1.8,0)
        low1=np.where((t>=low1_ps)&((t<21150) if not stuck else True),1.8,0)
        names=names+['v(xd.xr.low0)','v(xd.xr.high1)','v(xd.xr.low1)'];w=np.column_stack([w,low0,high1,low1])
        header=f'Flags: real\nNo. Variables: {len(names)}\nNo. Points: {len(t)}\nVariables:\n'
        header+=''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+w.astype('<f8').tobytes())

    def test_intermediate_order_and_stopped_clear_are_required_at_both_duties(self):
        mos=[dict(name='test',terminals=['0','VDD','RESET_N','XD:bad'],limit_v=1.95)]
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for duty in [.4,.6]:
                for level in [0,1]:
                    spec=dict(pilot.specifications()[0],duty=duty,stop_level=level)
                    self.raw(folder,spec);self.assertTrue(pilot.measure(folder,spec,mos)['counter_feasibility_passed'])
                    self.raw(folder,spec,low1_ps=5000)
                    self.assertFalse(pilot.measure(folder,spec,mos)['alternating_phase_order_passed'])
                    self.raw(folder,spec,stuck=True)
                    self.assertFalse(pilot.measure(folder,spec,mos)['stopped_clock_intermediate_clear_passed'])


if __name__=='__main__':unittest.main()
