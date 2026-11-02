# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import screen_receiver_differential_restore as screen
from layout import circuits
from spice_probes import ProbeNetwork


class DifferentialSourceScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical=(Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text()

    def test_observes_all_fourteen_or_nineteen_actual_mos_and_new_tail(self):
        for variant,count in [('control',14),('track_t8_r7',19),('track_t16_r7',19)]:
            source=screen.instrument(screen.factory.source_variant(self.canonical,variant))
            devices=screen.observed_devices(source)
            self.assertEqual(len(devices),count)
            self.assertIn('XTRACK/XP',devices);self.assertIn('XTRACK/XN',devices)
            if variant!='control':
                self.assertEqual(devices['XIB0/XN'][2],'sky130_fd_pr__nfet_01v8')
                self.assertEqual(devices['XAT'][1][0],'OBS_AMP_D')
                self.assertEqual(devices['XAT'][3]['w'],'8' if variant=='track_t8_r7' else '16')

    def test_zero_volt_meters_preserve_every_original_device_and_terminal(self):
        for variant in screen.VARIANTS:
            candidate=screen.factory.source_variant(self.canonical,variant)
            instrumented=screen.instrument(candidate)
            restored='\n'.join(line for line in instrumented.splitlines() if not line.startswith(('VOBS_','HOBS_')))+'\n'
            for label,node in [('TAIL','CT'),('REPLICA','NBC'),('AMP','AMP_CT')]:
                restored=restored.replace('OBS_'+label+'_D',node)
            self.assertEqual(circuits(restored),circuits(candidate))

    def test_new_probes_exist_without_changing_stimuli_or_numerical_policy(self):
        parent=Path('/old');folder=Path('/new')
        before=('Source fixture\n.include "/old/source.spice"\n'
            '.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
            'VIO VDDIO 0 3.3\nVDIG VDDD 0 1.8\nVREF VREF 0 1.2\nIREF IREF 0 35u\n'
            'VP P 0 PWL(0 0 12n .1)\nVN N 0 PWL(0 .1 12n 0)\n'
            'XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver\nCQ Q 0 100f\n'
            '.tran 10p 144n 0 50p\n.print tran V(P) V(N) V(Q)\n.end\n')
        for variant in screen.VARIANTS:
            source=screen.instrument(screen.factory.source_variant(self.canonical,variant))
            deck=screen.observe_deck(before,parent,folder,source)
            self.assertIn('.tran 10p 144n 0 50p',deck)
            self.assertIn('.options timeint method=gear reltol=1e-4 abstol=1e-12',deck)
            for line in before.splitlines():
                if line.startswith(('V','I','XR ','CQ ')):self.assertIn(line,deck.splitlines())
            probes=re.search(r'(?im)^\.print tran[^\n]*',deck)[0]
            ProbeNetwork(screen.probe_view(source)).validate(screen.probe_view(deck),re.findall(r'V\(([^)]+)\)',probes,re.I))
            self.assertIn('V(XR:XCORE:CO_TRACK)',probes)
            self.assertEqual('V(XR:XCORE:OBS_IAMP)' in probes,variant!='control')

    def test_missing_or_changed_amplifier_meter_cannot_hide_terminal_stress(self):
        source=screen.instrument(screen.factory.source_variant(self.canonical,'track_t8_r7'))
        with self.assertRaisesRegex(ValueError,'current meter'):
            screen.observed_devices(source.replace('VOBS_AMP AMP_CT OBS_AMP_D 0','VOBS_AMP AMP_CT OBS_AMP_D 0.1'))


if __name__=='__main__':
    unittest.main()
