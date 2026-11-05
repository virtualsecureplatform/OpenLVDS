# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_weighted_routed_v2 as pilot


class RoutedTimingPilotTests(unittest.TestCase):
    def test_unmatched_control_receipt_cannot_create_state_lock_or_request_a_solver(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            m={'identity':{'components':dict(clock='clock',fine_cells='fines',repair='repair')}}
            with patch.object(pilot,'bound',return_value=m),patch.object(pilot.control_gate,'require',side_effect=ValueError('unmatched controls')),patch.object(pilot,'lease') as lease,patch.object(pilot,'receipt_bound') as physical:
                with self.assertRaisesRegex(ValueError,'unmatched controls'):pilot.run(out,out/'unrelated')
                lease.assert_not_called();physical.assert_not_called()
            self.assertEqual(list(out.iterdir()),[])

    def test_native_terminal_order_and_actual_mos_and_control_nodes_reach_the_deck(self):
        witness=dict(ports=['VGND','OUT','VPWR','IN'],devices=[dict(terminals=['XD:d','XD:g','VDD','0'])],
                     controls=[dict(nodes=['XD:distributed.n0','XD:distributed.t0'])])
        with patch.dict(pilot.os.environ,{'PDK_ROOT':'/pdk'}):
            deck=pilot.fixture(Path('/prepared'),pilot.specifications()[0],witness)
        self.assertIn('XD 0 OUT VDD IN openlvds_weighted_bank_physical_v2\n',deck)
        self.assertIn('.tran 2p 60n 0 2p',deck)
        for n in ['XD:d','XD:g','XD:distributed.n0','XD:distributed.t0']:self.assertIn('V('+n+')',deck)
        self.assertIn('.options itl4=100',deck)


if __name__=='__main__':unittest.main()
