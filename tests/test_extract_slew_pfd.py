from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import extract_slew_pfd as extract
import spice_library


class StrictSlewPFDExtraction(unittest.TestCase):
    def test_preparation_keeps_physical_parent_immutable_and_binds_copied_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);parent,pdk,info,audit=self.fixture(root);(parent/'manifest.json').write_text('{}')
            old=extract.ROOT
            for n in extract.CODE:shutil.copyfile(old/'scripts'/n,root/'scripts'/n)
            sdk=root/'sdk/sky130A'
            files={'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice':'# cells\n',
                   'libs.tech/netgen/sky130A_setup.tcl':'# netgen\n','libs.tech/magic/sky130A.magicrc':'# magic\n','libs.tech/magic/sky130A.tech':'# tech\n'}
            for n,text in files.items():p=sdk/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            before=(parent/'summary.json').read_bytes()
            m={'identity':{'inputs':{},'code':{},'collateral':{}},'files':{}}
            with self.context(root),patch.dict(os.environ,{'PDK_ROOT':str(root/'sdk')}),patch.object(extract.physical,'verify',return_value={'passed':True}),patch.object(extract.physical,'bound',return_value=m),patch.object(extract.physical,'output_files',return_value=[]),patch.object(extract,'tool_context',return_value={}):
                out=extract.prepare(parent);captured=extract.bound(out)
                self.assertEqual(extract.prepare(parent),out)
                self.assertEqual((parent/'summary.json').read_bytes(),before)
                self.assertEqual((out/'summary.json').read_bytes(),before)
                self.assertFalse(captured['physical_admission'])
                (out/'summary.json').write_text('{}')
                with self.assertRaises(ValueError):extract.bound(out)

    def fixture(self, root):
        out=root/'build/diagnostics/slew_pfd_rc/fixture';out.mkdir(parents=True)
        archive=root/'physical/inputs';archive.mkdir(parents=True)
        cfg=dict(DESIGN_NAME='lvds_pfd',VERILOG_FILES=[str(archive/'lvds_pfd.v')])
        for n,text in {'lvds_pfd.v':'// physical fixture\n','pfd_blackboxes.v':'// blackbox\n','pfd.sdc':'# constraint\n','config.json':json.dumps(cfg)}.items():(archive/n).write_text(text)
        (out/'config.json').write_bytes((archive/'config.json').read_bytes())
        stamp=hashlib.sha256(b''.join((archive/n).read_bytes() for n in ('lvds_pfd.v','pfd_blackboxes.v','pfd.sdc','config.json'))).hexdigest()
        run=root/'physical/run';(run/'final/gds').mkdir(parents=True);(run/'final/spice').mkdir()
        gds=run/'final/gds/lvds_pfd.gds';gds.write_text('unit fixture only\n')
        scripts=root/'scripts';scripts.mkdir();(scripts/'extract.py').write_bytes((extract.ROOT/'scripts/extract.py').read_bytes())
        ports='DN FB PD_ENABLE REF RESET_N UP VGND VPWR'.split()
        model='nfet'
        physical=run/'final/spice/lvds_pfd.spice'
        physical.write_text('.subckt nfet D G S B\n.ends\n.subckt lvds_pfd '+' '.join(ports)+'\nX0 REF REF VGND VGND nfet w=1 l=.15\n.ends\n')
        pdk=root/'pdk';pdk.mkdir();cells=pdk/'cells.spice';cells.write_text('.subckt nfet D G S B\nM0 D G S B model w=1 l=.15\n.ends\n')
        setup=pdk/'setup.tcl';setup.write_text('# unit fixture\n')
        (out/'summary.json').write_text(json.dumps(dict(passed=True,interface_verified=True,source_sha256=stamp,run=str(run.relative_to(root)),input_archive=str(archive.relative_to(root)))))
        fingerprint=hashlib.sha256(gds.read_bytes()+(scripts/'extract.py').read_bytes()).hexdigest()
        folder=root/'build/extracted'/fingerprint[:16]/'lvds_pfd';folder.mkdir(parents=True)
        raw=folder/'lvds_pfd.rcx.spice';native=folder/'lvds_pfd.reduced.spice'
        raw.write_text('.subckt lvds_pfd '+' '.join(ports)+'\nX0 n3 REF VGND VGND nfet w=1 l=.15\nR1 REF n1 10\nR2 n1 n2 10\nR3 n2 n3 10\nC1 n3 VGND 1f\n.ends\n')
        reduction=extract.reduce_netlist(raw,native)
        info=dict(passed=True,ports_verified=True,returncode=0,ports=ports,resistors=3,capacitors=1,
                  source_sha256=stamp,gds_sha256=extract.sha(gds),fingerprint=fingerprint,reduction=reduction,
                  netlist=str(native.relative_to(root)),raw_netlist=str(raw.relative_to(root)),netlist_sha256=extract.sha(native))
        (out/'extraction.json').write_text(json.dumps(info))
        audit=out/'rc_audit';audit.mkdir();reference=audit/'reference.spice';reference.write_text(extract.legacy.reference_schematic(physical.read_text(),cells.read_text()))
        (audit/'wire_collapsed.spice').write_text(extract.collapse(native.read_text()))
        extract.strict_setup(audit/'setup.tcl',setup)
        report=audit/'lvs.log';report.write_text('Circuits match uniquely.\n')
        a=dict(passed=True,source_sha256=stamp,gds_sha256=extract.sha(gds),netlist_sha256=extract.sha(native),
               physical_spice_sha256=extract.sha(physical),pdk_cells_sha256=extract.sha(cells),reference_sha256=extract.sha(reference),
               report=str(report.relative_to(root)),report_sha256=extract.sha(report))
        (out/'rc_audit.json').write_text(json.dumps(a))
        return out,dict(cells=str(cells),setup=str(setup)),info,a

    def context(self,root):
        from contextlib import ExitStack
        stack=ExitStack()
        for module in (extract,extract.legacy,spice_library):stack.enter_context(patch.object(module,'ROOT',root))
        return stack

    def test_exact_reduction_and_strict_lvs_pass_without_claiming_phy_or_route_matching(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out,pdk,info,audit=self.fixture(root)
            with self.context(root):r=extract.model_evidence(out,pdk)
            self.assertTrue(r['passed']);self.assertTrue(r['exact_reduction_reproduced']);self.assertEqual(r['model']['reduction']['resistor_count_after'],1)
            self.assertFalse(r['route_matching_verified']);self.assertFalse(r['qualified_phy']);self.assertFalse(r['physical_admission'])

    def test_rehashed_resistor_or_capacitor_modification_cannot_pass_reduction_replay(self):
        for component in ('R','C'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);out,pdk,info,audit=self.fixture(root);native=root/info['netlist']
                if component=='R':native.write_text(native.read_text().replace('30','31'))
                else:native.write_text(native.read_text().replace('1f','2f'))
                info['netlist_sha256']=audit['netlist_sha256']=extract.sha(native)
                (out/'extraction.json').write_text(json.dumps(info));(out/'rc_audit.json').write_text(json.dumps(audit))
                with self.context(root),self.assertRaises(ValueError):extract.model_evidence(out,pdk)

    def test_ignored_properties_or_changed_setup_do_not_inherit_strict_lvs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out,pdk,info,audit=self.fixture(root);report=root/audit['report']
            report.write_text('Circuits match uniquely.\nwith property errors\n');audit['report_sha256']=extract.sha(report);(out/'rc_audit.json').write_text(json.dumps(audit))
            with self.context(root):self.assertFalse(extract.model_evidence(out,pdk)['passed'])
            (out/'rc_audit/setup.tcl').write_text('ignore all devices\n')
            with self.context(root),self.assertRaises(ValueError):extract.model_evidence(out,pdk)

    def test_wrong_public_interface_or_gds_binding_fails(self):
        for mutation in ('ports','gds'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);out,pdk,info,audit=self.fixture(root)
                if mutation=='ports':info['ports'][-1]='EXTRA'
                else:info['gds_sha256']='wrong'
                (out/'extraction.json').write_text(json.dumps(info))
                with self.context(root),self.assertRaises(ValueError):extract.model_evidence(out,pdk)

    def test_failed_physical_gate_creates_no_extraction_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(extract.physical,'verify',return_value={'passed':False}),self.assertRaisesRegex(ValueError,'passing PFD'):extract.prepare(root/'parent')
            self.assertEqual(list(root.iterdir()),[])

    def test_existing_or_partial_global_extraction_never_restarts_magic(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'out';out.mkdir();parent=root/'parent';parent.mkdir();(out/'manifest.json').write_text('{}')
            target=root/'existing';target.mkdir()
            with patch.object(extract,'ROOT',root),patch.object(extract,'bound',return_value={'identity':{'parent':'parent'}}),patch.object(extract,'extraction_directory',return_value=(target,'hash')),patch.object(extract.legacy,'run') as run:
                with self.assertRaisesRegex(ValueError,'no retry'):extract.run(out)
                run.assert_not_called()
