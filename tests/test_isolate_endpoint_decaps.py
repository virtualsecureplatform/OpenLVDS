# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import isolate_endpoint_decaps as endpoint
import test_isolate_tx_decap as fixtures


class EndpointDecapIsolation(unittest.TestCase):
    def test_rx_mapping_uses_actual_rx_pin_and_restores_tx_producer(self):
        args=list(fixtures.MappedDecapIsolation().fixture())
        args[0]=args[0].replace('openlvds_tx_core',endpoint.RX)
        args[1]=args[1].replace('"tx_serial"','"serial"')
        args[2]=args[2].replace('tx_serial','serial')
        original=endpoint.mapped.TOP,endpoint.mapped.registration
        with endpoint.rx_mapping():
            mapped=endpoint.mapped.mapped_devices(*args)
            self.assertEqual(len(mapped),112)
            self.assertEqual(endpoint.mapped.TOP,endpoint.RX)
        self.assertEqual((endpoint.mapped.TOP,endpoint.mapped.registration),original)
        result=endpoint.mapped.remove_mapped(args[0],mapped)
        self.assertIn('RRAIL VGND VGND.n1 214',result)
        self.assertIn('CPLATE VPWR VGND 1f',result)

    def test_missing_pin_or_mapping_failure_restores_original_producer(self):
        original=endpoint.mapped.TOP,endpoint.mapped.registration
        with self.assertRaisesRegex(ValueError,'unique RX serial'):
            with endpoint.rx_mapping():endpoint.mapped.registration('', '')
        self.assertEqual((endpoint.mapped.TOP,endpoint.mapped.registration),original)

    def test_terminal_wrong_failure_and_unrelated_namespaces_cannot_dispatch(self):
        with self.assertRaises(ValueError):endpoint.prepare(Path('/tmp/other'))
        with self.assertRaises(ValueError):endpoint.run(Path('/tmp/other'))


if __name__=='__main__':unittest.main()
