# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import tempfile
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import two_bank_native_measure_300_v1 as p


class RelativeTransportTests(unittest.TestCase):
    def setUp(self):
        self.s=dict(cycles=8,frequency_mhz=310,duty=.5,coarse=0,fine=0)
        self.t=np.arange(0,40001,dtype=float)

    def wave(self,delay=0,missing_first=False):
        v=np.zeros(len(self.t))
        for k in range(1 if missing_first else 0,8):
            rise=2100+k*1e6/310+delay;fall=rise+.5*1e6/310
            v+=1.8*np.minimum(np.clip((self.t-rise+50)/100,0,1),
                              np.clip((fall+50-self.t)/100,0,1))
        return v

    def test_second_bank_uses_measured_previous_output(self):
        source=self.wave(700);out=self.wave(1450)
        result=p.stage(self.t,source,out,self.s,ideal_input=False)
        self.assertTrue(result['stage_transport_passed'])
        self.assertEqual(result['input_reference'],'measured_previous_bank_output')
        self.assertIsNone(result['input_timing_stimulus_passed'])
        self.assertAlmostEqual(result['zero_code_fast_quarter_headroom_ps'],1e6/310/4-750,6)
        for edge in ('rise','fall'):
            self.assertTrue(all(abs(d-750)<1e-6 for d in result['edge_delays_ps'][edge]))
        wrong=p.stage(self.t,source,out,self.s,ideal_input=True)
        self.assertFalse(wrong['stage_transport_passed'])
        self.assertFalse(wrong['input_timing_stimulus_passed'])

    def test_startup_pulse_cannot_be_discarded(self):
        result=p.stage(self.t,self.wave(),self.wave(700,missing_first=True),self.s,ideal_input=True)
        self.assertFalse(result['stage_transport_passed'])
        self.assertFalse(result['all_input_output_pulses_present'])
        self.assertEqual(result['pulse_counts']['rise']['input'],8)
        self.assertEqual(result['pulse_counts']['rise']['output'],7)

    def test_downstream_zero_quarter_failure_preserved(self):
        result=p.stage(self.t,self.wave(700),self.wave(1600),self.s,ideal_input=False)
        self.assertFalse(result['stage_transport_passed'])
        self.assertFalse(result['zero_code_quarter_passed'])
        self.assertLess(result['zero_code_fast_quarter_headroom_ps'],0)
        self.assertTrue(result['repeated_delay_screen_passed'])

    def test_each_bank_checks_its_own_control_code(self):
        values={'0':np.zeros(len(self.t)),'VDD':np.full(len(self.t),1.8),
                'switch':np.full(len(self.t),1.8),'gate':np.full(len(self.t),1.8)}
        observation=dict(devices=[dict(name='M',terminals=['switch','gate','0','0'],limit_v=1.98)],
            controls=[dict(node='switch',control='fine0')],
            programming_gates=[dict(device='M',gate_node='gate',control='fine0',kind='fine')])
        high=p.electrical(self.t,values.__getitem__,observation,0,31)
        low=p.electrical(self.t,values.__getitem__,observation,0,0)
        self.assertTrue(high['control_settling_passed']);self.assertFalse(low['control_settling_passed'])
        self.assertTrue(high['terminal_screen_passed']);self.assertTrue(low['terminal_screen_passed'])

    def test_terminal_stress_includes_startup(self):
        values={'0':np.zeros(len(self.t)),'VDD':np.full(len(self.t),1.8)}
        values['VDD'][0]=2.1
        observation=dict(devices=[dict(name='M',terminals=['VDD','VDD','0','0'],limit_v=1.98)],
                         controls=[],programming_gates=[])
        result=p.electrical(self.t,values.__getitem__,observation,0,0)
        self.assertFalse(result['terminal_screen_passed'])
        self.assertEqual(result['terminal_stress'][0]['maximum_terminal_difference_v'],2.1)

    def binary_fixture(self,folder,*,fine=31,supply=1.8,start_ps=0):
        from dcdl_uniform_tree_v3 import encode
        values={'time':self.t*1e-12,'v(in)':self.wave(),'v(out)':self.wave(700),
                'v(next_out)':self.wave(1450),'v(vdd)':np.full(len(self.t),supply),
                'v(first_gate)':np.zeros(len(self.t)),
                'v(next_gate)':np.full(len(self.t),1.8 if fine else 0)}
        if start_ps:values['time']=values['time'][1:]
        for prefix,c,f in (('',0,0),('NEXT_',0,fine)):
            for pin,value in encode(c,f).items():
                values['v('+prefix.lower()+pin.lower()+')']=np.full(len(self.t),1.8*value)
        names=list(values)
        data=np.column_stack([v if len(v)==len(values['time']) else v[1:] for v in values.values()])
        header=('Title: synthetic two-bank metrology unit fixture\nFlags: real\n'
                f'No. Variables: {len(names)}\nNo. Points: {len(data)}\nVariables:\n'
                +''.join(f'\t{k}\t{n}\t'+('time' if k==0 else 'voltage')+'\n' for k,n in enumerate(names))
                +'Binary:\n')
        path=folder/'bench.raw'
        with path.open('wb') as handle:
            handle.write(header.encode());handle.write(data.astype('<f8').tobytes())
        observations={}
        for label,gate,a,b in (('first','first_gate','IN','OUT'),('next','next_gate','OUT','NEXT_OUT')):
            observations[label]=dict(devices=[dict(name=label+'M',terminals=[a,gate,b,'0'],limit_v=1.98)],
                controls=[dict(node=gate,control='fine0')],
                programming_gates=[dict(device=label+'M',gate_node=gate,control='fine0',kind='fine')])
        return observations

    def test_complete_binary_measurement_uses_distinct_stage_and_control_references(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);observations=self.binary_fixture(folder)
            result=p.measure(folder,observations,dict(self.s,stop_ns=40),next_coarse=0,next_fine=31)
            self.assertTrue(result['two_bank_zero_pilot_passed'])
            self.assertTrue(result['fixed_supply_passed']);self.assertFalse(result['qualified_phy'])
            self.assertTrue(result['banks']['first']['control_settling_passed'])
            self.assertTrue(result['banks']['next']['control_settling_passed'])
            self.assertEqual(len(result['banks']['next']['timing']['edge_delays_ps']['rise']),8)
            self.assertAlmostEqual(result['banks']['first']['timing']['edge_delays_ps']['rise'][0],700)
            self.assertAlmostEqual(result['banks']['next']['timing']['edge_delays_ps']['rise'][0],750)

    def test_supply_error_and_missing_dc_sample_cannot_pass_complete_measurement(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);observations=self.binary_fixture(folder,supply=1.9)
            result=p.measure(folder,observations,dict(self.s,stop_ns=40),next_coarse=0,next_fine=31)
            self.assertFalse(result['fixed_supply_passed']);self.assertFalse(result['two_bank_zero_pilot_passed'])
            observations=self.binary_fixture(folder,start_ps=1)
            with self.assertRaisesRegex(ValueError,'DC/startup'):
                p.measure(folder,observations,dict(self.s,stop_ns=40),next_coarse=0,next_fine=31)
