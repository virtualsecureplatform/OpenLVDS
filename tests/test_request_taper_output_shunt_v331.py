"""Ensure the startup repair preserves the full native counter and fixture."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import probe_request_taper_output_shunt_v331 as probe

PARENT=ROOT/'build/diagnostics/request_taper_forty_boundary_v330/ce0c4012334987a4'


class OutputShuntTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity=json.loads((PARENT/'manifest.json').read_text())['identity']
        cls.cells=(PARENT/'cells.spice').read_text()
        cls.module=(PARENT/'pair.spice').read_text()
        cls.devices=cls.identity['devices'][probe.candidate.VARIANT]

    def test_exactly_one_added_mim_and_all_original_mos(self):
        cells,module=probe.transform(self.cells,self.module,self.devices)
        before=probe.candidate.tapered.source.inventory.native_leaves(
            probe.candidate.tapered.collapse(self.cells+self.module),probe.candidate.source.source.HARNESS)[1]
        after=probe.candidate.tapered.source.inventory.native_leaves(
            probe.candidate.tapered.collapse(cells+module),probe.candidate.source.source.HARNESS)[1]
        self.assertEqual(len(after),len(before)+1)
        self.assertEqual(sum('cap_mim' in d['model'] for d in before),56)
        self.assertEqual(sum('cap_mim' in d['model'] for d in after),57)
        self.assertEqual(probe.candidate.source.observations(cells,module),self.devices)
        self.assertEqual(len(self.devices),808)
        self.assertEqual(cells.replace(probe.SHUNT+'\n',''),self.cells)
        self.assertEqual(module,self.module)

    def test_full_fixture_and_all_saved_vectors_unchanged(self):
        old=(PARENT/'0/bench.cir').read_text().splitlines()
        new=probe.fixture(PARENT,probe.specification(),self.devices).splitlines()
        self.assertEqual(old[1:],new[1:])
        self.assertNotEqual(old[0],new[0])
        self.assertIn('.tran 1p 26n 0 1p',new)
        self.assertEqual(probe.specification(),self.identity['spec'])

    def test_wrong_setter_or_double_application_rejected(self):
        wrong=self.cells.replace('Xlow0_set_pair CLK request_i low0_sn','Xlow0_set_pair CLK request_i wrong',1)
        with self.assertRaisesRegex(ValueError,'exact original guarded'):
            probe.transform(wrong,self.module,self.devices)
        cells,module=probe.transform(self.cells,self.module,self.devices)
        with self.assertRaisesRegex(ValueError,'exact original guarded'):
            probe.transform(cells,module,self.devices)


if __name__=='__main__':unittest.main()
