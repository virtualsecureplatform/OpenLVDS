# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_regenerated_bank_sparse_v63 as p


class NonzeroNativeTraceTests(unittest.TestCase):
    def fixture(self):
        spec=dict(p.zero.spec(),coarse=1,fine=16)
        levels=p.baseline.circuit.encode(spec['coarse'],spec['fine'])
        targets=p.control_targets(spec['coarse'],spec['fine']);control='fine0'
        node='XD:gate';device=dict(name='Mtest',terminals=['OUT',node,'0','0'],limit_v=1.95)
        obs=dict(devices=[device],controls=[dict(node=node,control=control)],
            programming_gates=[dict(device='Mtest',gate_node=node,control=control,kind='fine')])
        t=np.linspace(0,20e-9,2001)
        def wave(delay):return 1.8*sum(((t>=b+delay)&(t<b+4e-9+delay)).astype(float) for b in (2.1e-9,12.1e-9))
        columns={'time':t,'v(in)':wave(0),'v(out)':wave(.8e-9),'v(vdd)':np.full(len(t),1.8),
                 'v(xd.gate)':np.full(len(t),1.8*targets[control])}
        columns.update({'v('+k.lower()+')':np.full(len(t),1.8*v) for k,v in levels.items()})
        names=list(columns);values=np.column_stack(list(columns.values()))
        return dict(spec=spec,observations=obs),names,values

    def test_nonzero_controls_and_delay_above_quarter_are_legal_static_samples(self):
        i,n,w=self.fixture()
        with patch.object(p,'validate',return_value=(n,w)):
            r=p.measure_trace(Path('/unused'),i)
        self.assertTrue(r['static_native_screen_passed']);self.assertNotIn('zero_code_fast_quarter_headroom_ps',r)
        self.assertAlmostEqual(r['samples'][1]['rise_delay_ps'],800)

    def test_wrong_external_nonzero_control_is_rejected(self):
        i,n,w=self.fixture();levels=p.baseline.circuit.encode(i['spec']['coarse'],i['spec']['fine'])
        pin=next(k for k,v in levels.items() if v);w[:,n.index('v('+pin.lower()+')')]=0
        with patch.object(p,'validate',return_value=(n,w)):
            with self.assertRaisesRegex(ValueError,'External control'):p.measure_trace(Path('/unused'),i)

    def test_internal_programming_gate_movement_fails(self):
        i,n,w=self.fixture();w[:,n.index('v(xd.gate)')]=w[:,n.index('v(in)')]
        with patch.object(p,'validate',return_value=(n,w)):
            r=p.measure_trace(Path('/unused'),i)
        self.assertFalse(r['control_settling_passed']);self.assertFalse(r['static_native_screen_passed'])


if __name__=='__main__':unittest.main()
