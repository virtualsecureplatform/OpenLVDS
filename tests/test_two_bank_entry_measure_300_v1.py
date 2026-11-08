# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bank_entry_waveform_300_v1 as reference
import two_bank_entry_measure_300_v1 as p
import replay_tg2_loaded_native_300_v2 as reader
from replay_bank_300_v2 import same
from dcdl_uniform_tree_v3 import encode


class EntryBinaryReaderTests(unittest.TestCase):
    def fixture(self,folder,s,tamper=False):
        t=np.arange(40001,dtype=np.float64)
        output_spec=dict(s,input_slew_ps=20)
        values={'time':t*1e-12,'v(in)':reference.evaluate(t,s),
                'v(out)':reference.evaluate(t-700,output_spec),'v(next_out)':reference.evaluate(t-1400,output_spec),
                'v(vdd)':np.full(len(t),1.8),'v(first_gate)':np.zeros(len(t)),'v(next_gate)':np.zeros(len(t))}
        if tamper:values['v(in)'][2100]+=.001
        for prefix in ('','NEXT_'):
            for pin,value in encode(0,0).items():values['v('+prefix.lower()+pin.lower()+')']=np.full(len(t),1.8*value)
        names=list(values);data=np.column_stack(list(values.values()))
        header=('Title: synthetic entry-domain analyzer fixture\nFlags: real\n'
                f'No. Variables: {len(names)}\nNo. Points: {len(data)}\nVariables:\n'
                +''.join(f'\t{k}\t{n}\t'+('time' if k==0 else 'voltage')+'\n' for k,n in enumerate(names))+'Binary:\n')
        with (folder/'bench.raw').open('wb') as out:out.write(header.encode());out.write(data.astype('<f8').tobytes())
        observations={}
        for label,gate,a,b in (('first','first_gate','IN','OUT'),('next','next_gate','OUT','NEXT_OUT')):
            observations[label]=dict(devices=[dict(name=label+'M',terminals=[a,gate,b,'0'],limit_v=1.95)],
                controls=[dict(node=gate,control='fine0')],
                programming_gates=[dict(device=label+'M',gate_node=gate,control='fine0',kind='fine')])
        return observations

    def test_both_binary_readers_agree_at_all_boundary_settings(self):
        for slew,duty in ((250,.6),(250,.4),(20,.6),(20,.4)):
            s=dict(frequency_mhz=310,input_slew_ps=slew,duty=duty,cycles=8,stop_ns=40,coarse=0,fine=0)
            with tempfile.TemporaryDirectory() as folder:
                folder=Path(folder);o=self.fixture(folder,s)
                a=p.measure(folder,o,s,next_coarse=0,next_fine=0)
                b=p.measure(folder,o,s,next_coarse=0,next_fine=0,independent_reader=True)
                self.assertTrue(same(a,b));self.assertTrue(a['two_bank_zero_pilot_passed'])
                self.assertFalse(a['qualified_phy'])
                self.assertEqual(len(a['banks']['first']['timing']['edge_delays_ps']['rise']),8)
                self.assertNotIn('ideal_source_roundoff_allowance_ps',a['banks']['next']['timing'])

    def test_source_voltage_mismatch_is_not_an_acceptable_roundoff(self):
        s=dict(frequency_mhz=310,input_slew_ps=20,duty=.4,cycles=8,stop_ns=40,coarse=0,fine=0)
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);o=self.fixture(folder,s,tamper=True)
            a=p.measure(folder,o,s,next_coarse=0,next_fine=0)
            self.assertFalse(a['two_bank_zero_pilot_passed'])
            self.assertFalse(a['banks']['first']['timing']['ideal_source_waveform_passed'])

    def test_new_reader_accepts_eight_case_registry_and_refuses_pending_data(self):
        with tempfile.TemporaryDirectory(dir=reader.ROOT/'build') as folder:
            parent=Path(folder);(parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=reader.entry.VERSION))))
            with patch.object(reader.entry,'bound') as bound:
                with self.assertRaisesRegex(ValueError,'still pending: 7'):reader.run(parent,['7'])
                bound.assert_not_called()
            (parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=reader.early.VERSION))))
            with self.assertRaisesRegex(ValueError,'explicit unique'):reader.run(parent,['7'])
