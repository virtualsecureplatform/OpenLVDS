# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from driver_native_stress import terminal_observations,voltage_probes,measure


class ActualNativeMOSTerminals(unittest.TestCase):
    LIB='''.subckt driver A VA VS
XCORE A VA VS core
.ends driver
.subckt core IN VP VN
X0 VP.t0 IN.t0 VN.t0 VN sky130_fd_pr__nfet_g5v0d10v5 w=8 l=.5
R0 VP VP.t0 1
R1 IN IN.t0 1
R2 VN VN.t0 1
.ends core
'''
    def test_supply_ports_resolve_to_real_top_nodes_and_ground(self):
        rows=terminal_observations(self.LIB,'XD D VDDIO 0 driver')
        self.assertEqual(rows[0]['terminals'],dict(D='XD:XCORE:VP.t0',G='XD:XCORE:IN.t0',S='XD:XCORE:VN.t0',B='0'))
        self.assertEqual(len(voltage_probes(rows)),3)
        self.assertNotIn('XD:XCORE:VN',voltage_probes(rows))

    def test_signed_stress_uses_actual_source_voltage_and_requires_every_probe(self):
        rows=terminal_observations(self.LIB,'XD D VDDIO 0 driver')
        names=['time','v(xd.xcore.vp.t0)','v(xd.xcore.in.t0)','v(xd.xcore.vn.t0)']
        raw=np.array([[0.,3.2,1.8,.1],[1e-9,3.3,-.1,.05]])
        r=measure(names,raw,rows)['results'][0]['voltages']
        self.assertAlmostEqual(r['vgs']['max_v'],1.7)
        self.assertAlmostEqual(r['vgs']['min_v'],-.15)
        self.assertAlmostEqual(r['vbs']['min_v'],-.1)
        with self.assertRaises(ValueError):measure(names[:-1],raw[:,:-1],rows)

    def test_recursion_or_missing_instance_fails(self):
        with self.assertRaises(ValueError):terminal_observations(self.LIB,'XOTHER D VDDIO 0 driver')
        with self.assertRaises(ValueError):terminal_observations('.subckt loop A\nX1 A loop\n.ends loop','XD D loop')
