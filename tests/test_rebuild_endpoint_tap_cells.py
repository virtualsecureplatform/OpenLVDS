# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import rebuild_endpoint_tap_cells as endpoints


class EndpointPhysicalRebuild(unittest.TestCase):
    def test_both_designs_preserve_every_other_flow_and_rtl_setting(self):
        for name in endpoints.DESIGNS.values():
            config=dict(DESIGN_NAME=name,DECAP_CELLS=[],VERILOG_FILES=['original.v'],CLOCK_PERIOD=2.380952,STA_CORNERS=['nom','min','max'])
            actual=endpoints.tap_config(config)
            self.assertEqual({k:v for k,v in actual.items() if k not in ['ENDCAP_CELL','WELLTAP_CELL']},config)
            self.assertEqual(actual['ENDCAP_CELL'],endpoints.tx.TAP)
            self.assertEqual(actual['WELLTAP_CELL'],endpoints.tx.TAP)
        with self.assertRaises(ValueError):endpoints.tap_config(dict(DESIGN_NAME='unrelated',DECAP_CELLS=[]))

    def test_rx_uses_its_own_topology_checker_and_restores_after_failure(self):
        original=endpoints.tx.tx_buffered_paths_retained
        with patch.object(endpoints,'retained',return_value=True) as retained:
            with endpoints.physical_policy('rx','half-cycle-publish-buf4'):
                self.assertTrue(endpoints.tx.tx_buffered_paths_retained('RX cells',4))
                retained.assert_called_once_with('RX cells',strength=4,early_publish=True)
        self.assertIs(endpoints.tx.tx_buffered_paths_retained,original)
        with self.assertRaises(RuntimeError):
            with endpoints.physical_policy('rx','half-cycle-publish-buf4'):raise RuntimeError('controlled')
        self.assertIs(endpoints.tx.tx_buffered_paths_retained,original)

    def test_failed_or_partial_endpoint_isolation_cannot_launch_physical_flow(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(endpoints,'ROOT',Path(tmp)):
            p=Path(tmp)/'build/diagnostics/endpoint_decap_isolation/test';(p/'both_endpoints').mkdir(parents=True)
            (p/'manifest.json').write_text(json.dumps(dict(identity={},tasks=[dict(id='both_endpoints')])))
            for completed in [False,None]:
                (p/'both_endpoints/summary.json').write_text(json.dumps(dict(numerically_completed=completed,returncode=1)))
                with self.assertRaisesRegex(ValueError,'full twelve ns'):endpoints.causal_gate(p)

    def test_other_namespaces_cannot_launch_a_rebuild(self):
        with self.assertRaises(ValueError):endpoints.run(Path('/tmp/physical'))
        with self.assertRaises(ValueError):endpoints.causal_gate(Path('/tmp/physical'))


if __name__=='__main__':unittest.main()
