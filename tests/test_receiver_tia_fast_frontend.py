# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_tia_fast_frontend as factory
import receiver_tia_restore as tia
import screen_receiver_tia_fast_frontend as screen
import matrix_receiver_tia_fast_frontend as matrix
from layout import circuits

ROOT=Path(__file__).resolve().parents[1]


class FastTIAFrontend(unittest.TestCase):
    def setUp(self):self.canonical=(ROOT/'analog/openlvds.spice').read_text()

    def test_control_is_byte_identical_and_only_all_load_branches_are_duplicated(self):
        self.assertEqual(factory.source_variant(self.canonical,'control'),tia.source_variant(self.canonical,'control'))
        for variant in factory.VARIANTS[1:]:
            reference=tia.source_variant(self.canonical,variant.removeprefix('fast_'))
            candidate=factory.source_variant(self.canonical,variant)
            old=circuits(reference);new=circuits(candidate)
            self.assertEqual(old.keys(),new.keys())
            for top in old:
                if top!=factory.TOP:self.assertEqual(old[top],new[top])
            a={r[0]:r for r in old[factory.TOP][1]};b={r[0]:r for r in new[factory.TOP][1]}
            self.assertEqual({n:r for n,r in b.items() if not n.startswith('XFAST_')},a)
            self.assertEqual(len(b)-len(a),14)
            for name in factory.LOADS:
                copied='XFAST_'+name[1:]
                self.assertEqual(b[copied][1:],a[name][1:])
            self.assertEqual(new[factory.TOP][0],old[factory.TOP][0])
            self.assertEqual({n for n in b if n.startswith('XRFB')},{n for n in a if n.startswith('XRFB')})

    def test_malformed_or_already_modified_frontend_is_rejected(self):
        control=factory.source_variant(self.canonical,'control')
        for source in [control.replace('XRLPPD ','XREMOVED '),control.replace('XRBCPP0 ','XREMOVED '),control.replace('XRLPPD PP PPRB VSS','XRLPPD PP PPRB PB'),factory.source_variant(self.canonical,'fast_tia_r2')]:
            with self.assertRaises(ValueError):factory.transform(source,'fast_tia_r2')
        with self.assertRaises(ValueError):factory.source_variant(self.canonical,'other')

    def test_observation_still_covers_all_original_fourteen_mos(self):
        for variant in factory.VARIANTS:
            source=factory.source_variant(self.canonical,variant)
            observed=screen.observed_devices(screen.instrument(source))
            self.assertEqual(len(observed),14)
            self.assertTrue({'XC0','XC1','XCT','XIB0/XP','XIB0/XN','XTRACK/XP','XTRACK/XN'}<=set(observed))

    def test_each_variant_needs_its_own_complete_dc_and_stress_pass(self):
        def row(v):return dict(task=v,passed=True,metrics=dict(metrics=dict(passed=True)),terminal_observations=dict(observed_thin_guard_passed=True))
        cases=[dict(results=[row(v) for v in factory.VARIANTS]) for _ in range(15)]
        self.assertTrue(all(v['source_dc_passed'] for v in matrix.admission(cases).values()))
        changed=deepcopy(cases);changed[-1]['results'][1]['terminal_observations']['observed_thin_guard_passed']=False
        result=matrix.admission(changed)
        self.assertFalse(result['fast_tia_r2']['source_dc_passed']);self.assertTrue(result['fast_tia_r4']['source_dc_passed'])
        self.assertFalse(any(v['source_dc_passed'] for v in matrix.admission(cases[:6]).values()))


if __name__=='__main__':unittest.main()
