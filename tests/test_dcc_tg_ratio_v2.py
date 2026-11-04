# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_tg_ratio_v2 as circuit
import test_dcc_tg_combiner_v2 as fixture


class NativeTgRatioTests(unittest.TestCase):
    def test_only_eight_transmission_gate_widths_change(self):
        library=fixture.RealTgDccTests().library()
        library+='.subckt sky130_fd_sc_hd__buf_8 A VGND VNB VPB VPWR X\nX0 X A private VGND sky130_fd_pr__nfet_01v8 w=.64 l=.15\n.ends\n'
        original,_=circuit.baseline.source('tg1',library)
        for variant,spec in circuit.VARIANTS.items():
            text,metadata=circuit.source(variant,library)
            normalized=text.replace(circuit.NAME,circuit.baseline.NAME)
            old=[l for l in original.splitlines() if not l.startswith('Xtg_')]
            new=[l for l in normalized.splitlines() if not l.startswith('Xtg_')]
            self.assertEqual(old,new);self.assertEqual(metadata['hardware'],spec)
            pairs=list(zip([l.split() for l in original.splitlines() if l.startswith('Xtg_')],
                           [l.split() for l in normalized.splitlines() if l.startswith('Xtg_')]))
            self.assertEqual(len(pairs),8)
            for a,b in pairs:
                self.assertEqual(a[:6],b[:6]);self.assertEqual(a[7:],b[7:])
                width=spec['n_width_um'] if b[5]==circuit.baseline.N else spec['p_width_um']
                self.assertEqual(b[6],f'w={width:g}')


if __name__=='__main__':unittest.main()
