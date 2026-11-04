# SPDX-License-Identifier: GPL-3.0-only
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import extract_native_flat_v4 as extraction


class FlatExtractionPassivityGateTests(unittest.TestCase):
    def run_extraction(self,cap):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);gds=root/'cell.gds';gds.write_bytes(b'layout fixture')
            def magic(argv,cwd,**kw):
                (Path(cwd)/'cell.rcx.spice').write_text(f'.subckt cell_rcx A Y VGND\nR0 A n 10\nC0 n VGND {cap} $ **FLOATING\nX0 Y n VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15\n.ends cell_rcx\n')
                return SimpleNamespace(returncode=0)
            with patch.object(extraction,'ROOT',root),patch.object(extraction.subprocess,'run',side_effect=magic),patch.dict(os.environ,PDK_ROOT='/pdk'),contextlib.redirect_stdout(io.StringIO()):
                info=extraction.extract('cell',gds,'source',ports={'A':dict(x_um=0,y_um=0),'Y':dict(x_um=1,y_um=0),'VGND':dict(x_um=2,y_um=0)},source_scope='scope')
            script=next((root/'build/extracted').glob('*/cell/extract.tcl')).read_text()
            self.assertIn('extract no resistance',script);self.assertIn('ext2spice hierarchy off',script)
            self.assertIn('ext2spice subcircuit top on',script)
            return info

    def test_successful_magic_output_cannot_pass_with_negative_energy_vertex(self):
        info=self.run_extraction('-3.8f');self.assertFalse(info['passed']);self.assertIsNone(info['reduction'])
        self.assertTrue(info['passivity']['negative_energy_witness'])

    def test_positive_coupled_rc_is_preserved_and_reduced(self):
        info=self.run_extraction('3.8f');self.assertTrue(info['passed']);self.assertTrue(info['passivity']['elementwise_passive_passed'])
        self.assertIsNotNone(info['reduction'])


if __name__=='__main__':unittest.main()
