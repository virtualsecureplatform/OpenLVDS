# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus Verilog is provided by scripts/env.sh')
class IoRefTop(unittest.TestCase):
    def test_prbs_loopback_locks_and_detects_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/'tb.vvp'
            subprocess.run(['iverilog','-g2012','-o',str(image),str(ROOT/'examples/openlvds_io_ref_top.v'),
                str(ROOT/'models/openlvds_io_functional.v'),str(ROOT/'tb/tb_io_ref_top.v')],check=True)
            result=subprocess.run(['vvp',str(image)],check=True,capture_output=True,text=True)
        self.assertIn('PASS io_ref_top',result.stdout);self.assertNotIn('FAIL',result.stdout)

    def test_power_pin_views_share_one_port_order(self):
        for name in ['sky130/openlvds_io.v','models/openlvds_io_functional.v']:
            with tempfile.TemporaryDirectory() as folder:
                subprocess.run(['iverilog','-g2012','-DUSE_POWER_PINS','-o',str(Path(folder)/'x.vvp'),str(ROOT/name)],check=True)


if __name__=='__main__':unittest.main()
