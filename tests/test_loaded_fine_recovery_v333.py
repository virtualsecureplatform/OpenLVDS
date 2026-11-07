# SPDX-License-Identifier: GPL-3.0-only
"""Guard the recorded-waveform boundary and retained native recovery experiment."""
import json
from pathlib import Path
import re
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import probe_loaded_fine_recovery_v333 as probe

PARENT=ROOT/'build/diagnostics/two_stage_fine_bank_v322/4092d10edbdce08c'
MATERIALS=ROOT/'build/diagnostics/discharge_fine_driver_rc_v219/7a09244f3f729a64'


class LoadedFineRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity=json.loads((PARENT/'manifest.json').read_text())['identity']
        cls.bank=(PARENT/'bank.spice').read_text()
        report=json.loads((MATERIALS/'summary.json').read_text())
        row=next(r for r in report['rows'] if r['macro']==probe.MODELS['p24'])
        cls.p24=probe.source.source.cell_definition((ROOT/row['extraction']['netlist']).read_text(),probe.MODELS['p24'])
        cls.variants={v:probe.transform(cls.bank,cls.identity['observations'],cls.p24,v) for v in probe.MODELS}

    def test_all_31_cells_controls_and_original_baseline_terminal_maps_retained(self):
        text,obs=self.variants['baseline']
        original={d['name']:d for d in self.identity['observations']['devices']}
        self.assertEqual(len(obs['devices']),413)
        self.assertTrue(all(original[d['name']]==d for d in obs['devices']))
        self.assertEqual(len(obs['controls']),62)
        self.assertEqual(len(obs['programming_gates']),93)
        defs=probe.source.source.native.definitions(text)
        _,body=defs[probe.TOP]
        self.assertEqual(sum(w[0].startswith('Xfine_unit') for w in body),31)
        self.assertEqual([w for w in body if w[0]=='Rboundary'],[['Rboundary','selected','REPLAY','1m']])
        old=probe.source.source.native.definitions(self.bank)
        for name in old:
            if name!=probe.source.TOP:self.assertEqual(defs[name],old[name])

    def test_stronger_pullup_changes_only_loaded_driver(self):
        _,baseline=self.variants['baseline'];text,changed=self.variants['p24']
        self.assertEqual(len(changed['devices']),417)
        before={d['name']:d for d in baseline['devices'] if not d['name'].startswith('XD:Xfine_isolate:')}
        after={d['name']:d for d in changed['devices'] if not d['name'].startswith('XD:Xfine_isolate:')}
        self.assertEqual(before,after)
        self.assertEqual(changed['controls'],baseline['controls'])
        self.assertEqual(changed['programming_gates'],baseline['programming_gates'])
        rows=probe.source.source.native.definitions(text)[probe.TOP][1]
        self.assertEqual([w[-1] for w in rows if w[0]=='Xfine_isolate'],[probe.MODELS['p24']])
        self.assertEqual([w[-1] for w in rows if w[0]=='Xfine_regenerate1'],[probe.MODELS['baseline']])

    def test_complete_native_point_sequence_is_preserved_in_pwl(self):
        times=np.array([0.,1e-15,2.5e-9,25e-9]);values=np.array([0.,.001,1.801,-.002])
        text=probe.waveform(times,values)
        pairs=[list(map(float,line[2:].split())) for line in text.splitlines()[1:-1]]
        np.testing.assert_array_equal(np.array(pairs)[:,0],times)
        np.testing.assert_array_equal(np.array(pairs)[:,1],values)
        for bad in (np.array([1e-15,1e-12,2.5e-9,25e-9]),np.array([0.,1e-15,1e-15,25e-9]),np.array([0.,1e-15,2.5e-9,24e-9])):
            with self.assertRaisesRegex(ValueError,'every finite, ordered native point'):probe.waveform(bad,values)

    def test_actual_clock_stimulus_full_stop_and_all_retained_probes(self):
        identity=dict(self.identity,original_fixture=(PARENT/'1/bench.cir').read_text(),
                      observations={v:o for v,(_,o) in self.variants.items()})
        old=identity['original_fixture'].splitlines()
        for variant in probe.MODELS:
            text=probe.fixture(PARENT,identity,variant);lines=text.splitlines()
            for prefix in ('BIN ','.tran ','CLOAD '):
                self.assertEqual(next(l for l in lines if l.startswith(prefix)),next(l for l in old if l.startswith(prefix)))
            instance=next(l for l in lines if l.startswith('XD ')).split()
            ports=probe.source.source.native.definitions(self.variants[variant][0])[probe.TOP][0]
            self.assertEqual(len(instance[1:-1]),len(ports))
            probes=set(re.findall(r'V\(([^)]+)\)',next(l for l in lines if l.startswith('.print '))))
            self.assertTrue({n for d in identity['observations'][variant]['devices'] for n in d['terminals'] if n!='0'}<=probes)
            self.assertFalse(any(n.startswith('XD:tree') for n in probes))

    def test_missing_fine_cell_or_wrong_inverter_is_rejected(self):
        broken=self.bank.replace('Xfine_unit30 fine_node','Xunexpected30 fine_node',1)
        with self.assertRaisesRegex(ValueError,'all 31 native fine'):probe.transform(broken,self.identity['observations'],self.p24,'baseline')
        with self.assertRaisesRegex(ValueError,'Unknown retained'):probe.transform(self.bank,self.identity['observations'],self.p24,'other')
        shared=self.bank.replace('.ends '+probe.source.TOP,'Cshared fine_node VGND 1f\n.ends '+probe.source.TOP,1)
        with self.assertRaisesRegex(ValueError,'Shared top-level passives'):probe.transform(shared,self.identity['observations'],self.p24,'baseline')

    def test_failed_baseline_parity_or_safety_blocks_driver_experiment(self):
        result={k:True for k in ('all_input_output_pulses_present','input_timing_stimulus_passed',
            'full_swing_pulses_passed','unwrapped_native_epoch_passed','pulse_order_and_widths_passed',
            'terminal_screen_passed','control_settling_passed')}
        result.update(baseline_parity=dict(parity_passed=True),period_screen_passed=False)
        self.assertTrue(probe.baseline_usable(result))
        self.assertFalse(probe.baseline_usable(dict(result,baseline_parity=dict(parity_passed=False))))
        self.assertFalse(probe.baseline_usable(dict(result,terminal_screen_passed=False)))
        self.assertFalse(probe.baseline_usable(None))


if __name__=='__main__':unittest.main()
