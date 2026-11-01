# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from probe_driver_internal import aliases, instrument


class DriverInternalObservation(unittest.TestCase):
    def test_instrumentation_changes_only_library_binding_and_voltage_outputs(self):
        parent, root = Path('/parent'), Path('/new')
        deck = '.include "/parent/library.spice"\nVDD VDD 0 1.8\n.tran 20p 188.049n 0 100p\n.print tran V(Q)\n.end\n'
        probes = dict(clock='XCT:internal')
        modified = instrument(deck, parent, root, probes)
        restored = modified.replace('/new/library.spice', '/parent/library.spice').replace(' V(XCT:internal)', '')
        self.assertEqual(restored, deck)
        self.assertEqual(modified.count('.print tran'), 1)
        for invalid in [deck.replace('.print tran V(Q)\n', ''), deck + '.print tran V(OTHER)\n',
                        deck.replace('/parent/library.spice', '/elsewhere/library.spice')]:
            with self.assertRaises(ValueError):
                instrument(invalid, parent, root, probes)

    def test_requires_exact_native_bus_names_for_both_driver_instances(self):
        leaves = ['XLS__AD', 'XLS__AB', 'XLS__L', 'XLS__R', 'DP', 'DN']
        source = '.subckt openlvds_driver_core IN OUT\n' + '\n'.join(
            f'R{i} openlvds_driver_core__{leaf} OUT 1' for i, leaf in enumerate(leaves)) + '\n.ends openlvds_driver_core\n'
        selected = aliases(source)
        self.assertEqual(len(selected), 12)
        self.assertEqual(selected['clock_XLS__AD'], 'XCT:openlvds_driver_core__XLS__AD')
        self.assertEqual(selected['data_DN'], 'XDT:openlvds_driver_core__DN')
        with self.assertRaisesRegex(ValueError, 'observation bus'):
            aliases(source.replace('openlvds_driver_core__DP ', 'openlvds_driver_core__DP.t0 '))


if __name__ == '__main__':
    unittest.main()
