"""Cover zero-area contact cases as well as the actual native escape plan."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
try:
    import verify_counter_escape_contacts_v329 as checker
except ModuleNotFoundError as error:
    if error.name != 'klayout':
        raise
    checker = None


@unittest.skipIf(checker is None, 'requires pinned CAD KLayout interpreter')
class EscapeContactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity=json.loads((checker.planner.PARENT/'manifest.json').read_text())['identity']
        cls.proposed=checker.planner.routes(cls.identity)

    def test_actual_proposed_and_native_masks_have_no_boundary_contacts(self):
        self.assertEqual(checker.contacts(self.proposed['shapes']),[])
        self.assertEqual(checker.native_contacts(self.identity,self.proposed)
            ['foreign_native_m4_m5_contacts_including_boundaries'],0)

    def test_shared_edge_and_corner_are_contacts(self):
        a=dict(net='A',layer='metal4',rect=[0,0,1,1])
        for b in ([1,0,2,1],[1,1,2,2]):
            shapes=[a,dict(net='X',layer='metal4',rect=b)]
            self.assertEqual(checker.planner.different_net_overlaps(shapes),[])
            self.assertEqual(len(checker.contacts(shapes)),1)

    def test_native_interstage_edge_touch_is_rejected(self):
        i=self.identity;p=i['plan']['placements']['request_driver'];bad=deepcopy(self.proposed)
        bad['buffer_shapes'].append(dict(net='REQUEST',layer='metal4',cell='request_driver',
            kind='injected_native_edge_contact',rect=[p['x']+14.,p['y']+23.2,p['x']+14.2,p['y']+23.5]))
        # The earlier positive-area check cannot see this exact shared edge.
        checker.planner.native_mask_check(i,bad)
        with self.assertRaisesRegex(ValueError,'contacts foreign native metal4'):
            checker.native_contacts(i,bad)


if __name__=='__main__':unittest.main()
