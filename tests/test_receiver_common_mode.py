# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_common_mode as cm


class ReceiverCommonMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = cm.baseline.source_variant((cm.ROOT/'analog/openlvds.spice').read_text(), True)

    def equivalent(self, source, powered):
        rows = [r for r in cm.circuits(source)[cm.TOP][1] if r[0].startswith('XRLPP') or r[0] == 'XRBCPP']
        nodes = ['PP', 'PPRT', 'PPRB']; index = {n: i for i, n in enumerate(nodes)}
        rails = dict(VREF=1.2 if powered else 0, VDDD=1.8 if powered else 0, VSS=0)
        a = np.zeros((3, 3)); b = np.zeros(3)
        for _, terminals, _, _ in rows:
            x, y = terminals[:2]
            for u, v in [(x, y), (y, x)]:
                if u not in index:
                    continue
                j = index[u]; a[j, j] += 1
                if v in index:
                    a[j, index[v]] -= 1
                else:
                    b[j] += rails[v]
        if not powered:
            b[0] += 1
        return float(np.linalg.solve(a, b)[0])

    def test_actual_passive_network_centers_and_differential_resistance(self):
        for variant, center, resistance in [('control', .9, .5), ('reference_return', 1.2, .5), ('rail_pullup', 1.2, 1/3)]:
            source = cm.transform(self.source, variant)
            self.assertAlmostEqual(self.equivalent(source, True), center)
            self.assertAlmostEqual(self.equivalent(source, False), resistance)

    def test_only_declared_resistor_changes_modify_original_source_bytes(self):
        self.assertEqual(cm.transform(self.source, 'control'), self.source)
        expected = self.source.replace('XRLPPE PPRB VSS VSS ', 'XRLPPE PPRB VREF VSS ').replace('XRLPNE PNRB VSS VSS ', 'XRLPNE PNRB VREF VSS ')
        self.assertEqual(cm.transform(self.source, 'reference_return'), expected)
        added = cm.transform(self.source, 'rail_pullup')
        lines = [line for line in added.splitlines(keepends=True) if line.startswith('XRBC')]
        self.assertEqual(len(lines), 2)
        for line in lines:
            added = added.replace(line, '')
        self.assertEqual(added, self.source)

    def test_changed_baseline_and_repeated_correction_are_refused(self):
        for source in [self.source.replace('XRLPPE PPRB VSS VSS', 'XRLPPE PPRB VREF VSS'),
                       cm.transform(self.source, 'rail_pullup')]:
            with self.assertRaises(ValueError):
                cm.transform(source, 'rail_pullup')
        with self.assertRaises(ValueError):
            cm.transform(self.source, 'unbounded')

    def test_current_meters_keep_twelve_devices_observable(self):
        source = cm.instrument(cm.transform(self.source, 'reference_return'))
        devices = cm.observed_devices(source)
        self.assertEqual(len(devices), 12)
        self.assertEqual(devices['XCT'][1][0], 'OBS_TAIL_D')
        self.assertEqual(source.count('VOBS_TAIL CT OBS_TAIL_D 0'), 1)
        view = cm.probe_view(source)
        deck = 'XR P N Q VREF IREF NB VDDIO VDDD 0 openlvds_receiver_core\n'
        cm.ProbeNetwork(view).validate(deck, ['XR:OBS_ITAIL', 'XR:OBS_IREPLICA'])
        self.assertIn('HOBS_TAIL OBS_ITAIL VSS VOBS_TAIL 1', source)

    def test_partial_static_pilot_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root/'build/diagnostics/receiver_common_mode/test'; out.mkdir(parents=True)
            tasks = [dict(id=v, files={}) for v in cm.VARIANTS]
            for t in tasks:
                (out/t['id']).mkdir()
            raw = out/'control/bench.raw'; raw.write_bytes(b'partial retained')
            cm.atomic(out/'manifest.json', dict(identity=dict(simulator_provenance='test', code={}, inputs={}), tasks=tasks))
            with patch.object(cm, 'ROOT', root), patch.object(cm, 'provenance', return_value='test'):
                with self.assertRaisesRegex(ValueError, 'Partial common-mode pilot retained'):
                    cm.run(out)
            self.assertEqual(raw.read_bytes(), b'partial retained')


if __name__ == '__main__':
    unittest.main()
