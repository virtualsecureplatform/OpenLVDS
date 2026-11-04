# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import guarded_phase_clock_release_v3 as circuit
import probe_guarded_phase_clock_release_v3 as pilot
from native_binary_raw_v2 import validate
import test_guarded_phase_clock_release_v2 as original


class BufferedRequestPhaseReleaseTests(unittest.TestCase):
    def test_all_native_request_consumers_use_the_actual_rc_buffer(self):
        library='.subckt sky130_fd_sc_hd__dfrtp_1 CLK D RESET_B VGND VNB VPB VPWR Q\nX0 Q RESET_B private VNB sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends\n'
        c=circuit.components
        rc={c.MODELS['nand2_8']:dict(info=dict(ports=['A','B','Y','VGND','VPWR'])),
            c.MODELS['inv_8']:dict(info=dict(ports=['A','Y','VGND','VPWR'])),
            c.CLOCK_BUFFER:dict(info=dict(ports=['A','X','VGND','VPWR']))}
        text=circuit.source(library,rc,['private'],2)
        consumers=[row for row in text.splitlines() if 'REQUEST' in row.split()]
        self.assertEqual(len(consumers),2) # Subcircuit interface plus the real buffer input.
        self.assertIn('Xrequest_driver REQUEST request_i VGND VPWR '+c.CLOCK_BUFFER,consumers)
        self.assertEqual(text.count('XGUARD'),2)
        self.assertIn('Xr0__X0 ready0 request_i r0__private VGND',text)
        self.assertIn('Xarm_b armed request_i arm_qb',text)
        self.assertIn('Xrelease_b RESET_N request_i release_qb',text)

    def raw(self,folder,spec,delay_ps=200,missing_reassertion=False):
        original.GuardedPhaseReleaseTests().raw(folder,spec)
        names,w=validate(folder/'bench.raw',set(),26e-9);t=w[:,names.index('time')]*1e12
        request=np.interp(t-delay_ps,t,w[:,names.index('v(request)')])
        if missing_reassertion:request[t>=22500]=0
        names=names+['v(xd.xr.request_i)'];w=np.column_stack([w,request])
        header=f'Flags: real\nNo. Variables: {len(names)}\nNo. Points: {len(t)}\nVariables:\n'
        header+=''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+w.astype('<f8').tobytes())

    def test_request_must_propagate_causally_including_stopped_reassertion(self):
        spec=pilot.specifications()[0];mos=[dict(name='test',terminals=['0','VDD','RESET_N','XD:bad'],limit_v=1.95)]
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.raw(folder,spec);r=pilot.measure(folder,spec,mos)
            self.assertEqual(r['buffered_request_rise_delays_ps'],[200,200])
            self.assertTrue(r['counter_feasibility_passed'])
            self.raw(folder,spec,missing_reassertion=True)
            with self.assertRaisesRegex(ValueError,'event count'):pilot.measure(folder,spec,mos)
            self.raw(folder,spec,delay_ps=0)
            with self.assertRaisesRegex(ValueError,'Noncausal'):pilot.measure(folder,spec,mos)


if __name__=='__main__':unittest.main()
