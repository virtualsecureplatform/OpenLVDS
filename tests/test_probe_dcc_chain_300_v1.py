# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcc_chain_300_v1 as p
import test_dcc_chain_measure_300_v1 as fixtures


class CombinedControllerTests(unittest.TestCase):
    def test_actual_material_pair_changes_only_include_paths(self):
        out=p.ROOT/'build/unused-combined-controller-test'
        decks=[]
        for k in ('0','1'):
            original=(p.MATERIAL/k/'bench.cir').read_text();text=p.fixture(original,out);decks.append(text)
            for name in ('bank.spice','dcc.spice'):
                self.assertIn(f'.include "{out/name}"',text)
                text=text.replace(f'.include "{out/name}"',f'.include "{p.MATERIAL/name}"')
            self.assertEqual(text,original)
        self.assertEqual(decks[0].replace(p.materials.chain.SOURCE.numerical_trial.CARD+'\n',''),decks[1])

    def test_binary_pair_preserves_internal_failure_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);rows=[]
            for k in range(2):
                folder=out/str(k);folder.mkdir();obs,s=fixtures.CombinedBinaryTests().fixture(folder)
                names,w=p.validate(folder/'bench.raw',set(),40e-9)
                values={n:np.array(w[:,j]) for j,n in enumerate(names)}
                for dcc in range(2):
                    for n in ('a','b'):values[f'v(xdc{dcc}.{n})']=values['v(in)']
                del w
                names=list(values);data=np.column_stack(list(values.values()))
                header=('Title: synthetic pair reader fixture\nFlags: real\n'
                    f'No. Variables: {len(names)}\nNo. Points: {len(data)}\nVariables:\n'
                    +''.join(f'\t{j}\t{n}\t'+('time' if j==0 else 'voltage')+'\n' for j,n in enumerate(names))+'Binary:\n')
                (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
                # Pulse crossing and classification comparison are tested here;
                # actual pulse hold metrology has its own full binary tests.
                result=p.metrology.previous.measure(folder,obs,s)
                result['dcc']['0']['pulse_generators']={'a':dict(passed=True)}
                rows.append(dict(task=dict(id=str(k),centered=k==0,spec=s),error=None,result=result))
            pair=p.numerical_pair(out,rows)
            self.assertTrue(pair['passed']);self.assertTrue(p.pilot_passed(rows,pair))
            rows[1]['result']['dcc']['0']['pulse_generators']['a']['passed']=False
            self.assertFalse(p.numerical_pair(out,rows)['passed'])
            rows[1]['result']['combined_loading_transport_passed']=False
            self.assertFalse(p.pilot_passed(rows,pair))
            rows[1]['error']='native failure'
            self.assertFalse(p.numerical_pair(out,rows)['passed'])
            with self.assertRaises(ValueError):p.pilot_passed(rows[:1],pair)
