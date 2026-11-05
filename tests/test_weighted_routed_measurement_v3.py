# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_weighted_routed_v2 as previous
import weighted_routed_measurement_v3 as streaming


def fixture(folder,coarse=0,bad=None):
    t=np.linspace(0,60e-9,30001);width=100e-12/(2*np.arctanh(.8));codes=previous.CODES
    source=np.zeros(len(t));output=source.copy();bits=[source.copy() for _ in range(5)]
    for slot,code in enumerate(codes):
        start=slot*10e-9;delay=(500+80*coarse+3*code)*1e-12
        source+=.9*(np.tanh((t-start-2.1e-9)/width)-np.tanh((t-start-6.1e-9)/width))
        output+=.9*(np.tanh((t-start-2.1e-9-delay)/width)-np.tanh((t-start-6.1e-9-delay)/width))
        for bit in range(5):bits[bit][(t>=start)&(t<(slot+1)*10e-9)]=1.8*((code>>bit)&1)
    coarse_values=[np.full(len(t),1.8 if i<coarse else 0.) for i in range(15)]
    body=source.copy()*0;internal=bits[0].copy();tail=internal.copy();inverse=1.8-internal
    if bad=='body':body[(t>=53e-9)&(t<53.1e-9)]=-.3
    if bad=='control':tail[(t>=24e-9)&(t<24.1e-9)]-=.25
    if bad=='missing_pulse':output[(t>=22e-9)&(t<29e-9)]=0
    if bad=='nonfinite':output[100]=float('nan')
    names=['time','v(in)','v(out)',*[f'v(c{i})' for i in range(15)],*[f'v(b{i})' for i in range(5)],'v(body)','v(en)','v(en_tail)','v(enb)','v(enb_tail)','v(vdd)']
    data=np.column_stack([t,source,output,*coarse_values,*bits,body,internal,tail,inverse,inverse.copy(),np.full(len(t),1.8)])
    if bad=='short':data=data[t<59e-9]
    if bad=='late_start':data=data[t>=1e-9]
    header=('Title: fixture\nPlotname: Transient Analysis\nFlags: real\n'+
            f'No. Variables: {len(names)}\nNo. Points: {len(data)}\nVariables:\n'+
            ''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n')
    (folder/'bench.raw').write_bytes(header.encode()+np.asarray(data,dtype='<f8').tobytes())
    witness=dict(devices=[dict(name='Xn',terminals=['OUT','IN','0','BODY'],limit_v=1.95),dict(name='Xp',terminals=['OUT','IN','VDD','VDD'],limit_v=1.95)],
                 controls=[dict(kind='fine',bit=0,nodes=['EN','EN_TAIL']),dict(kind='fine_b',bit=0,nodes=['ENB','ENB_TAIL'])])
    return dict(coarse=coarse,codes=codes),witness


def normalized(value):
    return json.loads(json.dumps(value,default=lambda scalar:scalar.item()))


class StreamedRoutedMeasurementTests(unittest.TestCase):
    def test_matches_the_original_six_pair_and_window_oracle_with_json_scalars(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for coarse,bad in [(0,None),(1,None),(0,'body'),(0,'control'),(0,'missing_pulse')]:
                with self.subTest(coarse=coarse,bad=bad):
                    spec,witness=fixture(p,coarse,bad)
                    before=previous.measure(p,spec,witness);after=streaming.measure(p,spec,witness)
                    with self.assertRaises(TypeError):json.dumps(before)
                    self.assertEqual(after,normalized(before))
                    self.assertEqual(json.loads(json.dumps(after)),after)
                    self.assertTrue(all(type(s['pulse_integrity_passed']) is bool for s in after['samples']))

    def test_short_or_nonfinite_trace_cannot_be_recovered_as_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ['short','nonfinite','late_start']:
                spec,witness=fixture(Path(tmp),bad=bad)
                with self.assertRaises(ValueError):streaming.measure(Path(tmp),spec,witness)
