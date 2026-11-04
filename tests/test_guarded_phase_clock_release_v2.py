# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import guarded_phase_clock_release_v2 as circuit
import probe_guarded_phase_clock_release_v2 as pilot
from native_binary_raw_v2 import validate
import test_guarded_clock_prepare_pilot_v2 as original


class GuardedPhaseReleaseTests(unittest.TestCase):
    def raw(self,folder,spec,arm_ps=8800,arm_stuck=False):
        original.GuardedPreparePilotTests().raw(folder,spec)
        names,w=validate(folder/'bench.raw',set(),26e-9)
        t=w[:,names.index('time')]*1e12
        arm=np.where((t>=arm_ps)&((t<21300) if not arm_stuck else True),1.8,0)
        names=names+['v(xd.xr.armed)'];w=np.column_stack([w,arm])
        header=f'Flags: real\nNo. Variables: {len(names)}\nNo. Points: {len(t)}\nVariables:\n'
        header+=''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+w.astype('<f8').tobytes())

    def test_phase_release_requires_low_phase_arming_and_stopped_clear(self):
        mos=[dict(name='test',terminals=['0','VDD','RESET_N','XD:bad'],limit_v=1.95)]
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for duty in [.4,.6]:
                for level in [0,1]:
                    spec=dict(pilot.specifications()[0],duty=duty,stop_level=level)
                    self.raw(folder,spec);r=pilot.measure(folder,spec,mos)
                    self.assertTrue(r['counter_feasibility_passed'])
                    self.raw(folder,spec,arm_ps=7400)
                    self.assertFalse(pilot.measure(folder,spec,mos)['phase_arming_passed'])
                    self.raw(folder,spec,arm_stuck=True)
                    self.assertFalse(pilot.measure(folder,spec,mos)['counter_feasibility_passed'])

    def test_native_guards_preserve_transistors_and_only_two_readiness_ffs(self):
        library='.subckt sky130_fd_sc_hd__dfrtp_1 CLK D RESET_B VGND VNB VPB VPWR Q\nX0 Q CLK private VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends\n'
        rc={}
        rc[circuit.components.MODELS['nand2_8']]=dict(info=dict(ports=['A','B','Y','VGND','VPWR']))
        rc[circuit.components.MODELS['inv_8']]=dict(info=dict(ports=['A','Y','VGND','VPWR']))
        text=circuit.source(library,rc,['private'],2)
        self.assertEqual(text.count('XGUARD'),2);self.assertEqual(text.count('w=.65 l=.15'),2)
        self.assertNotIn('.ic',text)
        with self.assertRaisesRegex(ValueError,'actual native'):circuit.source(library,rc,['missing'],2)

    def test_full_dcc_reset_input_load_and_nand2_feedback(self):
        gates={tag:(model,pins) for tag,model,pins in circuit.phase_gates()}
        self.assertEqual(gates['arm_b'],('nand2_8',dict(A='armed',B='REQUEST',Y='arm_qb')))
        self.assertEqual(gates['release_b'],('nand2_8',dict(A='RESET_N',B='REQUEST',Y='release_qb')))
        self.assertTrue(all(m in ['nand2_8','inv_8'] for m,_ in gates.values()))
        rc={circuit.components.MODELS[n]:dict(info=dict(ports=['A','B','Y','VGND','VPWR'])) for n in ['nand2_4','nand2_8']}
        rc[circuit.components.CLOCK_BUFFER]=dict(info=dict(ports=['A','X','VGND','VPWR']))
        text=pilot.harness(rc)
        self.assertEqual(text.count('RESET_N VPWR prepare_load'),2)
        self.assertIn('RESET_N VPWR mask_load',text)


if __name__=='__main__':unittest.main()
