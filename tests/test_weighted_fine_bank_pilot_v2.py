# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_weighted_fine_bank_v2 as pilot


class WeightedBankPilotTests(unittest.TestCase):
    def test_rc_separated_bulk_and_ground_nodes_survive_recursive_mapping(self):
        c=pilot.circuit
        text='.subckt native A Y VGND VPWR\nX0 Y A VGND bulk.t0 sky130_fd_pr__nfet_01v8 w=1 l=.15\nR0 bulk.t0 VGND 2\nC0 Y VGND 1f\n.ends\n'
        text+='.subckt '+c.NAME+' '+' '.join(c.PORTS)+'\nXdrive IN OUT VSS VDD native\n.ends\n'
        ds=c.mapped_mos(text);self.assertEqual(len(ds),1)
        self.assertEqual(ds[0]['terminals'],['OUT','IN','0','XD:Xdrive:bulk.t0'])

    def test_code_update_stress_is_checked_outside_tagged_pulses(self):
        spec=pilot.specifications()[0];t=np.arange(0,50001,50,dtype=float);inp=np.zeros(len(t));out=np.zeros(len(t));codes=np.zeros(len(t),dtype=int)
        for i,code in enumerate(spec['codes']):
            b=i*10000;inp[(t>=b+2100)&(t<b+6100)]=1.8;out[(t>=b+2300)&(t<b+6300)]=1.8;codes[(t>=b)&(t<b+10000)]=code
        names=['time','v(in)','v(out)','v(vdd)','v(xd.bulk.t0)'];values=[t*1e-12,inp,out,np.full(len(t),1.8),np.where(t==10050,2.,0)]
        for bit in range(15):
            for n in [f'c{bit}',f'xd.coarse{bit}']:names.append('v('+n+')');values.append(np.zeros(len(t)))
        for bit in range(5):
            level=np.where((codes>>bit)&1,1.8,0)
            for n,v in [(f'b{bit}',level),(f'xd.fine{bit}',level),(f'xd.fine_b{bit}',1.8-level)]:names.append('v('+n+')');values.append(v)
        w=np.column_stack(values);header=f'Flags: real\nNo. Variables: {len(names)}\nNo. Points: {len(t)}\nVariables:\n'
        header+=''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'bench.raw').write_bytes(header.encode()+w.astype('<f8').tobytes())
            mos=[dict(name='test',terminals=['IN','OUT','0','XD:bulk.t0'])]
            result=pilot.measure(p,spec,mos)
        self.assertEqual([r['code'] for r in result['samples']],spec['codes'])
        self.assertAlmostEqual(result['samples'][0]['rise_delay_ps'],200)
        self.assertFalse(result['terminal_screen_passed']);self.assertFalse(result['qualified_phy'])


if __name__=='__main__':unittest.main()
