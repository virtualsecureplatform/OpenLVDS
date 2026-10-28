# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import spice_library


class DigitalScope(unittest.TestCase):
    def test_modified_rtl_cannot_reuse_extracted_gds(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            files=['rtl/openlvds_reset.v','rtl/openlvds_ddr_rx.v',
                   'constraints/rx.sdc','build/physical/rx/config.json']
            for name in files:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
            stamp=hashlib.sha256(b''.join((root/p).read_bytes() for p in files)).hexdigest()
            gds=root/'run/final/gds/openlvds_ddr_rx.gds'
            gds.parent.mkdir(parents=True);gds.write_bytes(b'fixture GDS')
            physical=dict(passed=True,run='run',source_sha256=stamp)
            (root/'build/physical/rx/summary.json').write_text(json.dumps(physical))
            info=dict(source_sha256=stamp,gds_sha256=hashlib.sha256(gds.read_bytes()).hexdigest())
            with patch.object(spice_library,'ROOT',root):
                self.assertEqual(spice_library.digital_current('openlvds_ddr_rx',info),info)
                (root/'rtl/openlvds_ddr_rx.v').write_text('changed RTL')
                with self.assertRaisesRegex(ValueError,'stale'):
                    spice_library.digital_current('openlvds_ddr_rx',info)

    def test_native_cell_interface_change_cannot_reuse_tx_gds(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            files=['rtl/openlvds_reset.v','rtl/openlvds_tx_core.v','rtl/openlvds_ddr_tx.v',
                   'sky130/tx_blackboxes.v','constraints/tx.sdc','build/physical/tx/config.json']
            for name in files:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
            stamp=hashlib.sha256(b''.join((root/p).read_bytes() for p in files)).hexdigest()
            gds=root/'run/final/gds/openlvds_tx_core.gds'
            gds.parent.mkdir(parents=True);gds.write_bytes(b'native TX GDS')
            physical=dict(passed=True,run='run',source_sha256=stamp)
            (root/'build/physical/tx/summary.json').write_text(json.dumps(physical))
            info=dict(source_sha256=stamp,gds_sha256=hashlib.sha256(gds.read_bytes()).hexdigest())
            with patch.object(spice_library,'ROOT',root):
                self.assertEqual(spice_library.digital_current('openlvds_tx_core',info),info)
                (root/'sky130/tx_blackboxes.v').write_text('changed native cell interface')
                with self.assertRaisesRegex(ValueError,'stale'):
                    spice_library.digital_current('openlvds_tx_core',info)


if __name__=='__main__':unittest.main()
