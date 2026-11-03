from copy import deepcopy
import itertools
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dll_slew_coverage as coverage


class RepairedSlewCoverage(unittest.TestCase):
    def setUp(self):
        self.requirements = json.loads((coverage.original.ROOT / 'requirements.json').read_text())

    def manifest(self, worst=('fs', 25)):
        specs = coverage.required_cases(self.requirements, worst)
        tasks = []
        for i, sig in enumerate(sorted(specs, key=repr)):
            spec = {k: v for k, v in zip(coverage.original.FIELDS, sig[1:-1]) if v is not None}
            if sig[-1]: spec['interruption'] = True
            if spec['kind'] == 'loop': spec['architecture'] = 'averaged_pfd_ota'
            if spec['kind'] == 'logic': spec['expected'] = True
            tasks.append(dict(id=str(i), spec=spec, fast_rc=sig[0]))
        return dict(identity={'slew_coverage': coverage.descriptor(self.requirements, worst)}, tasks=tasks)

    def test_all_pvt_native_balance_and_frequency_extremes_retain_original_suite(self):
        old = coverage.original.required_cases(self.requirements)
        new = coverage.required_cases(self.requirements, ('fs', 25))
        self.assertLess(old, new)
        self.assertEqual(len(coverage.check_native_coverage(self.manifest(), self.requirements)), len(new))
        for p, t, pair, offset in itertools.product(coverage.PROCESSES, coverage.TEMPERATURES, coverage.SLEWS, coverage.OFFSETS):
            self.assertIn(coverage.original.signature(coverage.phase(p, t, 400, pair, offset)), new)
        for p, t in [('ss', 40), ('fs', 25)]:
            for mhz, pair, offset in itertools.product((390, 410), coverage.SLEWS, coverage.OFFSETS):
                self.assertIn(coverage.original.signature(coverage.phase(p, t, mhz, pair, offset)), new)

    def test_coincident_worst_corner_deduplicates_and_captures_remain(self):
        a = coverage.required_cases(self.requirements, ('ss', 40))
        b = coverage.required_cases(self.requirements, ('fs', 25))
        self.assertEqual(len(b) - len(a), 28)
        capture = dict(duty=.4937)
        with_capture = coverage.required_cases(self.requirements, ('ss', 40), [capture])
        self.assertEqual(len(with_capture), len(a) + 1)

    def test_source_expansion_includes_matched_slew_faults_and_all_clocks(self):
        specs = coverage.source_specs(self.requirements)
        self.assertEqual(len(specs), 1215)
        self.assertEqual(len({coverage.original.signature(s) for s in specs}), len(specs))
        for p, t, mhz, pair in itertools.product(coverage.PROCESSES, coverage.TEMPERATURES, coverage.FREQUENCIES, ((100, 100), *coverage.SLEWS)):
            self.assertEqual({s['offset_ps'] for s in specs if (s['process'], s['temperature'], s['mhz'], (s['reference_slew_ps'], s['feedback_slew_ps'])) == (p, t, mhz, pair)}, set(coverage.SOURCE_OFFSETS))

    def test_old_count_missing_extra_duplicate_and_foreign_profiles_fail(self):
        good = self.manifest()
        for mutation in ['old', 'missing', 'extra', 'duplicate', 'version', 'count', 'architecture', 'logic']:
            m = deepcopy(good)
            if mutation == 'old': m['identity'].pop('slew_coverage')
            if mutation == 'missing': m['tasks'].pop()
            if mutation == 'extra': m['tasks'].append(dict(id='extra', spec=coverage.phase('tt', 25, 405, (20, 200), 0), fast_rc=False))
            if mutation == 'duplicate': m['tasks'].append(deepcopy(m['tasks'][0]))
            if mutation == 'version': m['identity']['slew_coverage']['version'] = 'other'
            if mutation == 'count': m['identity']['slew_coverage']['required_case_count'] = 336
            if mutation == 'architecture': next(t for t in m['tasks'] if t['spec']['kind'] == 'loop')['spec']['architecture'] = 'charge_pump'
            if mutation == 'logic': next(t for t in m['tasks'] if t['spec']['kind'] == 'logic')['spec']['expected'] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                coverage.check_native_coverage(m, self.requirements)

    def test_contract_rejects_supply_sweep_wrong_temperature_and_unknown_worst(self):
        for key, value in [('supply_sweep', True), ('digital_supply_v', 1.7), ('temperatures_c', [0, 25, 85]), ('process_corners', ['tt'])]:
            req = dict(self.requirements, **{key: value})
            with self.assertRaises(ValueError): coverage.source_specs(req)
        with self.assertRaises(ValueError): coverage.descriptor(self.requirements, ('ss', 85))
