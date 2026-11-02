# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from driver_compact_geometry import physical_info


class DriverHierarchyBounds(unittest.TestCase):
    def test_child_plate_bounds_extend_beyond_access_wires(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            (out/'wrapper.mag').write_text('''magic
tech sky130A
magscale 1 2
<< metal3 >>
rect -10 -10 10 10
use capacitor I0
transform 1 0 100 0 1 -200
box -3600 -3600 3600 3600
<< labels >>
rlabel metal3 0 0 0 0 0 C1
<< end >>
''')
            info=physical_info(out,'wrapper')
            self.assertEqual(info['bbox'],[-17.5,-19.,18.5,17.])
            self.assertEqual(info['ports']['C1'],('metal3',0.,0.))
