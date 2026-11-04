# SPDX-License-Identifier: GPL-3.0-only
from collections import Counter
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_nand_latch_v2 as circuit


class StaticNandDccTests(unittest.TestCase):
    def test_only_native_static_gates_and_explicit_symmetric_compound_boundaries(self):
        gates=circuit.gates(2);self.assertEqual(len(gates),31)
        self.assertEqual({m for _,m,_ in gates},{'nand2_1','nand2_2','nand2_8','inv_1'})
        driven=Counter(p['Y'] for _,_,p in gates)
        self.assertEqual({n:c for n,c in driven.items() if c!=1},dict(xor_n=2,xor_a=2,xor_b=2,xor_out=2))
        self.assertEqual(driven['clock_out'],1)
        available=set(circuit.PORTS)|set(driven)
        self.assertTrue(all(n in available for _,_,p in gates for n in p.values()))
        with self.assertRaisesRegex(ValueError,'Undeclared'):circuit.gates(4)

    def test_native_transistor_values_are_preserved_with_private_nodes_per_gate(self):
        library=''
        for model,ports,nodes in [('nand2_1','A B VGND VNB VPB VPWR Y','Y A private VGND'),
                                  ('nand2_8','A B VGND VNB VPB VPWR Y','Y B private VGND'),
                                  ('inv_1','A VGND VNB VPB VPWR Y','Y A VGND VGND')]:
            library+=f'.subckt sky130_fd_sc_hd__{model} {ports}\nX0 {nodes} sky130_fd_pr__nfet_01v8 w=.64 l=.15\n.ends\n'
        text=circuit.source(1,library)
        self.assertEqual(text.count('w=.64 l=.15'),31)
        self.assertIn('Xxor_n_0__X0 xor_n a xor_n_0__private VGND',text)
        self.assertIn('Xxor_n_1__X0 xor_n b xor_n_1__private VGND',text)
        self.assertIn('.subckt '+circuit.NAME+' '+' '.join(circuit.PORTS),text)

    def test_three_value_unit_gate_simulation_initializes_and_toggles_without_async_ff(self):
        # Structural logic test only. Native SPICE, rather than these uniform
        # unit delays, must establish race margin, pulse timing and stress.
        cells=circuit.gates(1)
        def nand(a,b):return 1 if a==0 or b==0 else 0 if a==1 and b==1 else None
        for duty in [30,70]:
            values={p['Y']:None for _,_,p in cells};sources=[];outputs=[];previous={n:0 for n in ['phase0','phase180']};last_q=None
            for t in range(1130):
                inputs=dict(phase0=int(t>=10 and (t-10)%100<duty),phase180=int(t>=60 and (t-60)%100<duty),reset_n=int(t>=325))
                for phase in previous:
                    if inputs[phase] and not previous[phase] and t>=325:sources.append((t,phase))
                previous={n:inputs[n] for n in previous};old=dict(values,**inputs);updates={}
                for _,model,pins in cells:
                    out=(None if old[pins['A']] is None else 1-old[pins['A']]) if model=='inv_1' else nand(old[pins['A']],old[pins['B']])
                    updates.setdefault(pins['Y'],[]).append(out)
                values={n:vs[0] if all(v==vs[0] for v in vs) else None for n,vs in updates.items()}
                q=values['clock_out']
                if t>5 and t<325:self.assertEqual(q,1)
                if t>=325 and q!=last_q:outputs.append((t,q))
                last_q=q
            self.assertFalse(any(t<sources[0][0] for t,_ in outputs))
            for (a,phase),(b,_) in zip(sources,sources[1:]):
                events=[(t,q) for t,q in outputs if a<=t<b]
                self.assertEqual(len(events),1,(duty,a,phase,events))
                self.assertEqual(events[0][1],1 if phase=='phase0' else 0)


if __name__=='__main__':unittest.main()
