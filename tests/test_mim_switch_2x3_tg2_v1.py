# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout
import mim_switch_2x3_v2 as original
import mim_switch_2x3_tg2_v1 as changed
import inspect_mim_switch_2x3_tg2_pcells_v1 as inspection


class DoubleSwitchTests(unittest.TestCase):
    def test_only_transmission_switch_widths_change(self):
        old=layout.circuits(original.schematic())[original.NAME]
        new=layout.circuits(changed.schematic())[changed.NAME]
        self.assertNotEqual(original.NAME,changed.NAME)
        self.assertEqual(old[0],new[0]);self.assertEqual(len(new[1]),5)
        for a,b in zip(old[1],new[1]):
            self.assertEqual(a[:3],b[:3])
            if a[0] in ('XSWN','XSWP'):
                self.assertAlmostEqual(float(b[3]['w']),2*float(a[3]['w']))
                self.assertEqual({k:v for k,v in a[3].items() if k!='w'},
                                 {k:v for k,v in b[3].items() if k!='w'})
            else:self.assertEqual(a,b)

    def test_partial_primitive_execution_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);(out/'state.json').write_text('{"status":"inspecting"}')
            with patch.object(inspection,'bound',return_value=None):
                with self.assertRaisesRegex(ValueError,'Retain prior'):
                    inspection.run(out)
