# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_analog as runner

ROOT=Path(__file__).resolve().parents[1]
REQ=json.loads((ROOT/'io_300.json').read_text())['requirements']


def trace(edge_ps,ripple_v=0.,overshoot_v=0.):
    """Ideal loaded driver trace: DC plateaus, then PRBS7 with linear edges."""
    ui=1000/620;bits=runner.prbs7(254);points=[(0,-.35),(1900,-.35),(1900+edge_ps/1000,.35),(2000,.35),(2000+edge_ps/1000,-.35)]
    previous=0
    for i,bit in enumerate(bits,1):
        if bit!=previous:
            at=2000+i*ui;a,b=(-.35,.35) if bit else (.35,-.35)
            points += [(at,a),(at+edge_ps/1000,b+np.sign(b)*overshoot_v),(at+edge_ps/1000+.2,b)]
        previous=bit
    t=np.arange(0,2000+256*ui,.002);d=np.interp(t,[x for x,_ in points],[y for _,y in points])
    cm=1.25+ripple_v/2*np.sign(np.sin(2*np.pi*t/ui))
    return np.column_stack([np.arange(len(t)),t*1e-9,np.zeros(len(t)),cm+d/2,cm-d/2]),ui


class VerifyAnalogIo300(unittest.TestCase):
    def setUp(self):
        patcher=patch.multiple(runner,REQ=REQ,CONTRACT='io_300.json');patcher.start();self.addCleanup(patcher.stop)

    def measure(self,edge_ps,**kwargs):
        wave,ui=trace(edge_ps/.6,**kwargs)  # 20-80% is 0.6 of a linear edge
        return runner.driver_waveform_metrics(wave,2000+8*ui,2000+256*ui,ui)

    def test_edge_window_follows_shortest_unit_interval(self):
        self.assertAlmostEqual(runner.contract_ui_ns(),1000/620)
        good=self.measure(400)
        self.assertTrue(good['passed'],good)
        self.assertAlmostEqual(good['transition_limits_ps'][1],483.87,places=2)
        self.assertAlmostEqual(good['transition_max_ps'],400,delta=3)
        self.assertFalse(self.measure(240)['transition_within_limits'])
        self.assertFalse(self.measure(500)['transition_within_limits'])

    def test_common_mode_and_ring_limits(self):
        self.assertFalse(self.measure(400,ripple_v=.16)['common_mode_within_limit'])
        self.assertTrue(self.measure(400,ripple_v=.14)['common_mode_within_limit'])
        self.assertFalse(self.measure(400,overshoot_v=.16)['ring_within_limit'])

    def test_missing_plateau_fails_closed(self):
        wave,ui=trace(600);wave[:,3]=wave[:,4]
        self.assertFalse(runner.driver_waveform_metrics(wave,2000+8*ui,2000+256*ui,ui)['passed'])

    def test_imbalance(self):
        point=lambda vod,vos:dict(differential_mean_v=vod,common_mode_mean_v=vos)
        self.assertTrue(runner.driver_imbalance(dict(points=[point(.31,1.25),point(.33,1.22)]))['passed'])
        self.assertFalse(runner.driver_imbalance(dict(points=[point(.31,1.25),point(.37,1.25)]))['passed'])
        self.assertFalse(runner.driver_imbalance(dict(points=[point(.31,1.19),point(.31,1.25)]))['passed'])
        self.assertFalse(runner.driver_imbalance({})['passed'])

    def test_prbs7_stimulus(self):
        bits=runner.prbs7(254)
        self.assertEqual(bits[:127],bits[127:]);self.assertEqual(sum(bits[:127]),64)
        stimulus,stop,score=runner.driver_stimulus()
        times=[t for t,_ in stimulus]
        self.assertEqual(times,sorted(times));self.assertGreater(stop,times[-1]);self.assertLess(score,stop)

    def test_legacy_stimulus_unchanged(self):
        with patch.object(runner,'CONTRACT',None):
            stimulus,stop,score=runner.driver_stimulus()
        self.assertEqual((len(stimulus),stop,score),(5+2*432,2540,2510))

    def link_wave(self,amplitude,delay_ns=1.5,flip=None):
        ui=1000/620;bits=runner.prbs7(300);t=np.arange(0,20+304*ui,.005)
        def nrz(lag,low,high,edge):
            points=[(0,low)];previous=0
            for i,bit in enumerate(bits):
                if i==flip:bit=1-bit
                if bit!=previous:points += [(20+i*ui+lag-edge/2,high if previous else low),(20+i*ui+lag+edge/2,high if bit else low)]
                previous=bit
            return np.interp(t,[x for x,_ in points],[y for _,y in points])
        d=np.interp(t,*zip(*self.stimulus(bits,ui)));vr=nrz(delay_ns,-amplitude,amplitude,.4);q=nrz(delay_ns+.6,0,1.8,.2)
        return np.column_stack([np.arange(len(t)),t*1e-9,d,1.2+vr/2,1.2-vr/2,q]),bits,ui

    def stimulus(self,bits,ui):
        points=[(0,0.)];previous=0
        for i,bit in enumerate(bits):
            if bit!=previous:points += [(20+i*ui-.05,1.8*previous),(20+i*ui+.05,1.8*bit)]
            previous=bit
        return points

    def test_link_eye_and_bit_errors(self):
        wave,bits,ui=self.link_wave(.3)
        good=runner.link_metrics(wave,bits,20,ui)
        self.assertTrue(good['passed'],good)
        self.assertAlmostEqual(good['rx_pin_eye_height_v'],.3,delta=.01)
        self.assertGreater(good['output_valid_width_ps'],1000)
        wave,bits,ui=self.link_wave(.09)
        self.assertFalse(runner.link_metrics(wave,bits,20,ui)['rx_pin_eye_open'])

    def test_link_detects_a_wrong_bit(self):
        wave,bits,ui=self.link_wave(.3,flip=150)
        # Flipping one received run changes the transition pattern or the sampled value.
        self.assertFalse(runner.link_metrics(wave,bits,20,ui)['passed'])

    def test_channel_ladder_preserves_delay_and_impedance(self):
        for delay in [.1,1.2]:
            lines=runner.channel_ladder(0,'A','B',50,delay)
            l=sum(float(x.split()[3][:-1]) for x in lines if x.startswith('L'));c=sum(float(x.split()[3][:-1]) for x in lines if x.startswith('C'))
            self.assertAlmostEqual((l*c*1e-3)**.5,delay,places=6)    # sqrt(nH*pF)=ns*sqrt(1e-3)... total delay
            self.assertAlmostEqual((l/c*1e3)**.5,50,places=6)        # sqrt(nH/pF)=ohm*sqrt(1e3)
            self.assertEqual(lines[-1].split()[1],'B');self.assertEqual(lines[0].split()[1],'A')
            self.assertLessEqual(delay*1000/(len(lines)/2),50+1e-9)

    def test_timing_slews_span_the_driver_edge_window(self):
        slews=runner.timing_slews_ps()
        self.assertEqual(slews[0],260.);self.assertAlmostEqual(slews[2],.3*1e6/580,places=2)
        self.assertEqual(slews,sorted(slews))

    def test_thin_oxide_span_uses_supply_and_probe_extremes(self):
        t=np.linspace(0,1e-9,5);wave=np.column_stack([np.arange(5),t,np.full(5,.9),np.linspace(-.05,1.85,5)])
        ok=runner.stress_metrics(wave,3,['A'],[('D',2)])
        self.assertTrue(ok['passed']);self.assertAlmostEqual(ok['thin_oxide_terminal_span_v'],1.9)
        self.assertAlmostEqual(ok['limit_v'],1.93)   # 1.95 V device limit less the 20 mV measurement guard
        wave[:,3]=np.linspace(-.1,1.84,5)
        self.assertFalse(runner.stress_metrics(wave,3,['A'])['passed'])

    def test_supply_metrics_average_each_window(self):
        t=np.linspace(0,80e-9,801);quiet=t<29e-9
        wave=np.column_stack([np.arange(len(t)),t,np.where(quiet,-8e-3,-9e-3),np.where(quiet,-.2e-3,-1.2e-3),np.full(len(t),-4e-6)])
        got=runner.supply_metrics(wave,(10,28),(45,78))
        self.assertTrue(got['passed']);self.assertAlmostEqual(got['quiet']['vddio_ma'],8.);self.assertAlmostEqual(got['active']['vddd_ma'],1.2)
        self.assertAlmostEqual(got['active']['power_mw'],9*3.3+1.2*1.8);self.assertAlmostEqual(got['quiet']['vref_ua'],4.)
        self.assertFalse(runner.supply_metrics(wave[:10],(10,28),(45,78))['passed'])

    def test_mismatch_rule_is_mean_plus_three_sigma(self):
        def rows(offsets):
            return {f'receiver_mc_tt_25_s{i}':dict(passed=True,values={'1.2':dict(offset_v=v)}) for i,v in enumerate(offsets,1)}
        tight=runner.mismatch_statistics('receiver-mc',rows([.010,-.012,.008,-.006,.004]))['receiver_mc_tt_25']
        self.assertTrue(tight['passed'],tight)
        wide=runner.mismatch_statistics('receiver-mc',rows([.040,-.042,.038,-.036,.034]))['receiver_mc_tt_25']
        self.assertFalse(wide['passed'])
        same=runner.mismatch_statistics('receiver-mc',rows([.01]*5))['receiver_mc_tt_25']
        self.assertFalse(same['passed'])  # identical draws mean mismatch was not applied
        broken=rows([.01,-.01,.0]);broken['receiver_mc_tt_25_s2']=dict(passed=False,values={'1.2':None})
        self.assertFalse(runner.mismatch_statistics('receiver-mc',broken)['receiver_mc_tt_25']['passed'])

    def test_mismatch_requires_ngspice(self):
        with patch.object(runner,'engine',return_value='xyce'),self.assertRaises(ValueError):
            runner.mismatch_header('tt',25,1)

    def test_contract_must_be_local_io_schema(self):
        with self.assertRaises(ValueError):runner.use_contract('../outside.json')
        with self.assertRaises(ValueError):runner.use_contract('clocking_300mhz.json')

    def test_ngspice_supply_ramp_starts_after_time_zero(self):
        from run_ngspice import delay_ramps
        self.assertEqual(delay_ramps('VIO VDDIO 0 PWL(0 0 1n 3.3)\nIREF IREF 0 PWL(0 0 1n 35u)'),
            'VIO VDDIO 0 PWL(0 0 0.1n 0 1n 3.3)\nIREF IREF 0 PWL(0 0 0.1n 0 1n 35u)')
        from run_ngspice import trapezoidal
        self.assertEqual(trapezoidal('.options klu\n.options method=gear reltol=1e-4 abstol=1e-12\n.tran 1p 1n'),
            '.options klu\n.options reltol=1e-4 abstol=1e-12\n.tran 1p 1n')
        data='VD D 0 PWL(0 0 99.95n 0 100.05n 1.8)'
        self.assertEqual(delay_ramps(data),data)


if __name__=='__main__':unittest.main()
