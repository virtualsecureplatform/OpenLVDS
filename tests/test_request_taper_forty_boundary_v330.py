"""Keep the new stress-boundary trial tied to the real unchanged candidate."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import probe_request_taper_forty_boundary_v330 as probe

PARENT=ROOT/'build/diagnostics/request_taper_counter_v317/a9021aae03b1ad1c'
CAUSE=ROOT/'build/reports/matched_counter_stress/20261107T034837Z'


class CounterBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity=json.loads((PARENT/'manifest.json').read_text())['identity']

    def test_exact_newly_measured_boundary(self):
        spec=probe.specification()
        self.assertEqual((spec['process'],spec['temperature'],spec['mhz'],spec['duty'],spec['stop_level']),
                         ('ss',0,410,.4,0))
        self.assertEqual(spec['input_slew_ps'],100)
        self.assertEqual(spec['buffer_variant'],probe.candidate.VARIANT)

    def test_completed_sixty_fixture_changes_only_clock_duty_and_title(self):
        old=(PARENT/'0/bench.cir').read_text().splitlines()
        new=probe.fixture(PARENT,probe.specification(),self.identity['devices'][probe.candidate.VARIANT]).splitlines()
        self.assertEqual(len(old),len(new))
        changed=[(a,b) for a,b in zip(old,new) if a!=b]
        self.assertEqual(len(changed),2)
        self.assertTrue(changed[0][0].startswith('OpenLVDS '))
        self.assertTrue(changed[1][0].startswith('VRCLK RCLK 0 PWL('))
        self.assertIn('.tran 1p 26n 0 1p',new)
        self.assertEqual(next(v for v in old if v.startswith('.print ')),next(v for v in new if v.startswith('.print ')))

    def test_actual_native_terminal_map_is_unchanged(self):
        devices=probe.candidate.source.observations((PARENT/'cells.spice').read_text(),(PARENT/'pair.spice').read_text())
        self.assertEqual(devices,self.identity['devices'][probe.candidate.VARIANT])
        self.assertEqual(len(devices),808)

    def test_incomplete_stress_diagnosis_is_rejected(self):
        report=json.loads((CAUSE/'summary.json').read_text());report['all_stored_failed_peaks_reproduced']=False
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'summary.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'Require exact completed unchanged'):
                probe.require_cause(folder)

    def test_reassertion_only_reference_is_rejected(self):
        report=json.loads((CAUSE/'summary.json').read_text());report['case']=report['case'].rsplit('/',1)[0]+'/1'
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'summary.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'Require exact completed unchanged'):
                probe.require_cause(folder)


if __name__=='__main__':unittest.main()
