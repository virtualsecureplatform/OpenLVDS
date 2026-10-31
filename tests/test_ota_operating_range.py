# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import characterize_dll_ota as ota


class OTAOperatingRange(unittest.TestCase):
    def test_low_common_mode_fixture_keeps_supplies_and_bias_fixed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'requirements.json').write_text(json.dumps(dict(process_corners=['ff'],temperatures_c=[0])))
            source=root/'source.spice'
            source.write_text('.subckt lvds_phase_ota UF DF OUT PB VDDIO VDDD VSS\n'
                'X0 OUT UF VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=1\n.ends lvds_phase_ota\n'
                '.subckt lvds_bias IREF NB VDDIO VSS\n'
                'X0 NB NB VSS VSS sky130_fd_pr__nfet_01v8 w=2 l=1\n.ends lvds_bias\n')
            with patch.object(ota,'ROOT',root),patch.object(ota,'provenance',return_value='fixture'),patch.dict('os.environ',PDK_ROOT='/pdk'):
                out=ota.prepare(source,[.32,.34,.36],[.82,.84])
                manifest=json.loads((out/'manifest.json').read_text())
                deck=(out/'ff_0/bench.cir').read_text()
                self.assertEqual(len(manifest['grid']),18)
                for text in ['VA VDDIO 0 3.3','VD VDDD 0 1.8','IB PB 0 35u']:
                    self.assertIn(text,deck)
                self.assertEqual(out,ota.prepare(source,[.32,.34,.36],[.82,.84]))
                self.assertNotEqual(out,ota.prepare(source,[.34],[.84]))
                with self.assertRaises(ValueError):ota.prepare(source,[0],[.84])
