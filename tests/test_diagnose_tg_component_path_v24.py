# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_tg_component_path_v24 as diagnosis


class MeasuredNativeTerminalPathTests(unittest.TestCase):
    def test_component_connectivity_selects_real_terminal_vectors_without_public_node_inference(self):
        cells = ('.subckt component A Y VGND VPWR\nR1 Y drain 1\nR2 A gate 1\nC1 drain VGND 1f\n'
                 'XN drain gate VGND VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends component\n')
        bank = '.subckt bank IN OUT VPWR VGND\nXfoo IN OUT VGND VPWR component\n.ends bank\n'
        devices = [dict(name='XD:Xfoo:XN', model='sky130_fd_pr__nfet_01v8',
                        terminals=['XD:Xfoo:drain', 'XD:Xfoo:gate', '0', '0'])]
        self.assertEqual(diagnosis.terminal_group(cells, bank, devices, 'Xfoo', 'Y', (0, 2)), ['XD:Xfoo:drain'])
        self.assertEqual(diagnosis.terminal_group(cells, bank, devices, 'Xfoo', 'A', (1,)), ['XD:Xfoo:gate'])
        with self.assertRaises(ValueError):
            diagnosis.terminal_group(cells, bank, [], 'Xfoo', 'Y', (0, 2))

    def write(self, folder, missing=False, glitch=False):
        t = np.linspace(0, 20e-9, 2001)
        def pulse(delay):
            return ((t >= 2.1e-9+delay) & (t < 6.1e-9+delay) | (t >= 12.1e-9+delay) & (t < 16.1e-9+delay)).astype(float)
        native = 1.8*(1-pulse(.1e-9))
        if glitch:
            native[(t >= 8e-9) & (t < 8.5e-9)] = 0
        data = np.column_stack([t, 1.8*pulse(0), native, 1.8*pulse(.2e-9)])
        names = ['time', 'v(in)', 'v(missing)' if missing else 'v(xd.xfoo.drain)', 'v(out)']
        header = f'Title: native terminal bands\nFlags: real\nNo. Variables: 4\nNo. Points: {len(t)}\nVariables:\n'
        header += ''.join(f'{i} {name} voltage\n' for i, name in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+data.astype('<f8').tobytes())
        return [('input', ['IN'], True), ('actual_native', ['XD:Xfoo:drain'], False), ('output', ['OUT'], True)]

    def test_both_pulse_directions_use_only_actual_saved_crossings(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); selected = self.write(folder)
            rows = diagnosis.measure(folder, selected)
            self.assertEqual(len(rows), 4)
            for row in rows:
                self.assertGreater(row['public_input_to_output_delay_ps'], 190)
                self.assertLess(row['public_input_to_output_delay_ps'], 210)
                self.assertEqual(row['bands'][1]['terminals'][0]['node'], 'XD:Xfoo:drain')
                self.assertEqual(len(row['native_terminal_intervals']), 2)

    def test_missing_native_vector_or_extra_native_crossing_is_fatal(self):
        for missing, glitch in ((True, False), (False, True)):
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory); selected = self.write(folder, missing, glitch)
                with self.assertRaises(ValueError):
                    diagnosis.measure(folder, selected)


if __name__ == '__main__':
    unittest.main()
