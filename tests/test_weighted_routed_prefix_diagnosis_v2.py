# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_weighted_routed_prefix_v2 import prefix,terminal_observations,payload_sha


def raw(path,rows,names=None):
    names=names or ['time','v(out)','v(gate)','v(body)']
    header=('Title: fixture\nDate: test\nPlotname: Transient Analysis\nFlags: real\n'
            f'No. Variables: {len(names)}\nNo. Points: 0\nVariables:\n'+
            ''.join(f'{i}\t{n}\tvoltage\n' for i,n in enumerate(names))+'Binary:\n').encode()
    path.write_bytes(header+np.asarray(rows,dtype='<f8').tobytes())


class RoutedPrefixTests(unittest.TestCase):
    def test_append_and_final_point_count_update_do_not_change_consumed_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'raw';raw(p,[[0,1,0,0],[1e-9,1.96,1.7,-.01]])
            names,w,a,offset=prefix(p,2)
            with p.open('ab') as f:f.write(struct.pack('<4d',2e-9,1.8,1.8,0)+b'partial')
            data=p.read_bytes().replace(b'No. Points: 0',b'No. Points: 3');p.write_bytes(data)
            _,_,b,_=prefix(p,2);self.assertEqual(a,b)
            self.assertEqual(a['payload_sha256'],payload_sha(p,offset,a['payload_bytes']))
            device=dict(name='Xn',model='native',terminals=['OUT','GATE','0','BODY'],limit_v=1.95)
            r=terminal_observations(names,w,[device]);self.assertEqual(r['violating_devices'],1)
            self.assertAlmostEqual(r['rows'][0]['peak_v'],1.97)
            self.assertEqual((r['rows'][0]['highest_role'],r['rows'][0]['lowest_role']),('drain','body'))
            self.assertAlmostEqual(r['rows'][0]['peak_time_ps'],1000)

    def test_ground_and_gate_driven_violation_are_screened_as_all_six_pairs(self):
        names=['time','v(net)','v(out)'];w=np.array([[0,0,0],[1e-9,1.97,.005]])
        devices=[dict(name='Xmerge',model='native',terminals=['OUT','NET','0','0'],limit_v=1.95)]
        r=terminal_observations(names,w,devices)
        self.assertEqual(r['highest_terminal_role_counts'],{'gate':1})
        self.assertEqual(r['screened_native_mos'],1);self.assertTrue(r['six_terminal_pairs_per_device'])
        self.assertAlmostEqual(r['rows'][0]['peak_v'],1.97)

    def test_incomplete_nonfinite_nonmonotonic_ambiguous_and_missing_vectors_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'raw'
            for rows in [[[0,0,0,0],[0,1,1,0]],[[0,0,0,0],[1e-9,float('nan'),1,0]]]:
                raw(p,rows)
                with self.assertRaises(ValueError):prefix(p,2)
            raw(p,[[0,0,0,0],[1e-9,1,1,0]])
            with self.assertRaises(ValueError):prefix(p,3)
            raw(p,[[0,0,0,0],[1e-9,1,1,0]],['time','v(out)','v(out)','v(body)'])
            with self.assertRaises(ValueError):prefix(p,2)
        d=dict(name='Xn',terminals=['MISSING','0','0','0'],limit_v=1.95)
        with self.assertRaises(ValueError):terminal_observations(['time','v(out)'],np.zeros((2,2)),[d])
        d['terminals']=['OUT','0','0','0'];d['limit_v']=2.0
        with self.assertRaises(ValueError):terminal_observations(['time','v(out)'],np.zeros((2,2)),[d])
