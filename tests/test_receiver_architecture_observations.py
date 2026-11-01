# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re,sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_architecture_observations as obs
from receiver_architectures import transform,VARIANTS
from layout import circuits

class ArchitectureObservations(unittest.TestCase):
    def base(self):
        return obs.experiment.source_variant((obs.ROOT/'analog/openlvds.spice').read_text(),False)

    def test_meters_preserve_original_devices_and_zero_voltage_connections_for_all_variants(self):
        for variant in VARIANTS:
            plain=transform(self.base(),variant);instrumented=obs.instrument(self.base(),variant)
            self.assertEqual(instrumented.count('VOBS_TAIL CT OBS_TAIL_D 0'),1)
            self.assertEqual(instrumented.count('HOBS_TAIL OBS_ITAIL VSS VOBS_TAIL 1'),1)
            restored=re.sub(r'(?m)^[VH]OBS_[^\n]*\n','',instrumented)
            for node,label in obs.METERS.values():restored=restored.replace('OBS_'+label+'_D',node)
            self.assertEqual(restored,plain)

    def test_deck_observes_currents_without_inventing_internal_aliases_for_public_ports(self):
        deck='fixture\n.include "/parent/source.spice"\nVIO VDDIO 0 3.3\nVDIG VDDD 0 1.8\n.print tran V(P) V(N) V(Q)\n.end\n'
        text=obs.observe_deck(deck,Path('/parent'),Path('/child'))
        self.assertIn('HOBS_IO OBS_IIO 0 VIO 1',text);self.assertIn('V(OBS_IIO)',text)
        self.assertIn('V(IREF)',text);self.assertNotIn('V(XR:XCORE:PB)',text)
        for bad in [deck.replace('3.3','3.2'),deck.replace('.end','')]:
            with self.assertRaises(ValueError):obs.observe_deck(bad,Path('/parent'),Path('/child'))

    def fixture(self):
        names=['TIME','V(P)','V(N)','V(Q)']
        core=['PP','PN','CO','CL','CT','NBC','OBS_ITAIL','OBS_IREPLICA','OBS_TAIL_D','OBS_REPLICA_D']
        names+=['V(XR:XCORE:'+n+')' for n in core]+['V(IREF)','V(VDDIO)','V(VDDD)','V(OBS_IIO)','V(OBS_IDIG)']
        headers={n:i+1 for i,n in enumerate(names)};times=np.array([0,5,10,22,34,46,58,70,82,94,106,118,130,142,144])*1e-9
        wave=np.zeros((len(times),len(names)+1));wave[:,1]=times
        values={'P':1.25,'N':1.15,'Q':1.8,'XR:XCORE:PP':.95,'XR:XCORE:PN':.85,
            'XR:XCORE:CO':.9,'XR:XCORE:CL':1.3,'XR:XCORE:CT':.12,'XR:XCORE:NBC':.7,
            'XR:XCORE:OBS_TAIL_D':.12,'XR:XCORE:OBS_REPLICA_D':.7,
            'XR:XCORE:OBS_ITAIL':-100e-6,'XR:XCORE:OBS_IREPLICA':12e-6,
            'IREF':2.5,'VDDIO':3.3,'VDDD':1.8,'OBS_IIO':-250e-6,'OBS_IDIG':-50e-6}
        for n,v in values.items():wave[:,headers['V('+n+')']]=v
        rows={r[0]:r for r in circuits(transform(self.base(),'lvt'))[obs.TOP][1]}
        return wave,headers,rows

    def test_signed_current_power_and_between_sample_stress_are_measured(self):
        wave,headers,rows=self.fixture();result=obs.observations(wave,headers,rows)
        self.assertTrue(result['observed_thin_guard_passed'])
        self.assertAlmostEqual(result['currents']['tail']['signed_samples_a'][0],-100e-6)
        self.assertAlmostEqual(result['currents']['tail']['absolute_samples_a'][0],100e-6)
        self.assertAlmostEqual(result['fixture_supply_measurements']['io']['delivered_power_samples_w'][0],825e-6)
        wave[1,headers['V(XR:XCORE:NBC)']]=2.1;wave[1,headers['V(XR:XCORE:OBS_REPLICA_D)']]=2.1
        result=obs.observations(wave,headers,rows)
        self.assertFalse(result['observed_thin_guard_passed'])
        self.assertEqual(result['devices']['XNCB']['maximum_terminal_difference']['time_ns'],5.)

    def test_missing_meters_or_nonzero_sense_voltage_are_rejected(self):
        wave,headers,rows=self.fixture()
        wave[1,headers['V(XR:XCORE:OBS_TAIL_D)']]+=.01
        with self.assertRaisesRegex(ValueError,'terminal potential'):obs.observations(wave,headers,rows)
        wave,headers,rows=self.fixture();del headers['V(OBS_IIO)']
        with self.assertRaisesRegex(ValueError,'supply-current'):obs.observations(wave,headers,rows)

    def test_profile_preserves_parent_measurement_and_restores_all_bindings(self):
        previous=(obs.experiment.transform,obs.experiment.rebind,obs.experiment.measured,obs.experiment.CODE)
        with self.assertRaisesRegex(ValueError,'held'):
            with obs.profile('pmos_p8_t4'):
                self.assertIs(obs.experiment.measured,previous[2]);self.assertIn(obs.NAME,obs.experiment.CODE)
                raise ValueError('held')
        self.assertEqual((obs.experiment.transform,obs.experiment.rebind,obs.experiment.measured,obs.experiment.CODE),previous)

if __name__=='__main__':unittest.main()
