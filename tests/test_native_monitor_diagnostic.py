# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from diagnose_native_monitor import expose, monitor_nodes


class NativeMonitorDiagnostic(unittest.TestCase):
    def extracted(self):
        # Extraction preserves logical terminal names, but renames instances
        # and may reverse source/drain. Probe terminals rather than instances.
        rows = ['.subckt openlvds_dll_analog ' + ' '.join('P' + str(i) for i in range(15))]
        for i, name in enumerate(['PA', 'PB', 'XPOS__O', 'XPOS__OB',
                                  'XPOS__L', 'XPOS__T', 'POS', 'XNEG__O',
                                  'LOW', 'HIGH', 'S']):
            rows.append(f'X{i} dll_monitor_island.openlvds_dll_analog__XAREA__{name}.t2 '
                        'G S B sky130_fd_pr__nfet_01v8 w=8 l=1')
        rows.append('X98 VDDD.t290 openlvds_dll_analog__PC.t21 '
                    'dll_monitor_island.openlvds_dll_analog__XAREA__XPOS__T.t13 '
                    'VDDD.t289 sky130_fd_pr__pfet_01v8 ad=2.32 w=8 l=.5')
        rows.append('.ends openlvds_dll_analog')
        return '\n'.join(rows) + '\n'

    def test_actual_extracted_terminals_and_tail_bias_are_selected(self):
        groups = monitor_nodes(self.extracted())
        self.assertEqual(groups['PC_POS'], ['openlvds_dll_analog__PC.t21'])
        self.assertEqual(groups['VDDD_POS'], ['VDDD.t289', 'VDDD.t290'])
        self.assertEqual(len(groups['XPOS__T']), 2)
        self.assertEqual(groups['XPOS__O'],
                         ['dll_monitor_island.openlvds_dll_analog__XAREA__XPOS__O.t2'])
        self.assertNotIn(groups['XPOS__OB'][0], groups['XPOS__O'])

    def test_missing_terminal_group_cannot_silently_remove_a_probe(self):
        source = self.extracted().replace('__XAREA__HIGH.t2', '__XAREA__OTHER.t2')
        with self.assertRaisesRegex(ValueError, 'missing: HIGH'):
            monitor_nodes(source)

    def test_dc_clamps_only_add_ports_and_preserve_all_native_elements(self):
        source = self.extracted().replace(' P12 P13 P14', '\n+ P12 P13 P14')
        result = expose(source, ['UF.t1', 'DF.t2', 'CTRL.t3'])
        self.assertIn('+ P12 P13 P14 UF.t1 DF.t2 CTRL.t3\n', result)
        self.assertEqual(source[source.index('\nX0'):], result[result.index('\nX0'):])
        with self.assertRaisesRegex(ValueError, 'Invalid diagnostic'):
            expose(source, ['P0', 'DF.t2', 'CTRL.t3'])
        with self.assertRaisesRegex(ValueError, 'Invalid diagnostic'):
            expose(source, ['UF.t1', 'UF.t1', 'CTRL.t3'])
