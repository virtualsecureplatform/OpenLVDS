# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import measured_native_parameter_view_v155 as p


class ContinuedNativeInventoryTests(unittest.TestCase):
    def fixture(self,top,wrapped):
        ports=['IN','OUT','VPWR','VGND',*[f'E{k}' for k in range(31)]]
        header='.subckt '+top+' '+' '.join(ports)
        if wrapped:header='.subckt '+top+' '+' '.join(ports[:8])+'\n+ '+' '.join(ports[8:])
        rows=[header]
        for k in range(1453):
            row=f'X{k} OUT IN VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15 ad=.1 as=.1 pd=1 ps=1'
            if wrapped:row=row.replace(' ad=', '\n+ ad=')
            rows.append(row)
        rows += [f'XC{k} OUT VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2' for k in range(42)]
        return '\n'.join(rows+['.ends '+top,''])

    def test_wrapped_port_and_mos_cards_pass_without_changing_source_bytes(self):
        reference=self.fixture('native',True);extracted=self.fixture('rc',False)
        original=(reference,extracted);r=p.verify(reference,'native',extracted,'rc','b2')
        self.assertTrue(r['native_parameters_preserved']);self.assertEqual((r['native_mos'],r['native_mims']),(1453,42))
        self.assertEqual((reference,extracted),original);self.assertFalse(r['qualified_phy'])

    def test_normalization_preserves_strict_parameter_census_and_port_gates(self):
        reference=self.fixture('native',True);extracted=self.fixture('rc',False)
        changed=[extracted.replace('w=1 l=.15','w=2 l=.15',1),
                 extracted.replace('XC0 OUT VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2\n','',1),
                 extracted.replace('.subckt rc IN OUT','.subckt rc OUT IN',1)]
        for text in changed:
            with self.assertRaises(ValueError):p.verify(reference,'native',text,'rc','b2')


if __name__=='__main__':unittest.main()
