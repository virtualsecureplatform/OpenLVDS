# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import promote_phy_candidate as promotion


class SealedPHYRelease(unittest.TestCase):
    def test_changed_pfd_policy_invalidates_a_saved_passing_report(self):
        from pfd_candidate_policy import policy_provenance
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'bundle';bundle.mkdir();(bundle/'manifest.json').write_text('{}')
            scripts=root/'scripts';scripts.mkdir()
            names=['check_release.py','staged_release.py','dll_native_evidence.py','verify_candidate_rtl.py',
                   'pfd_candidate_policy.py','pfd_fast_reset_policy.py','physical_policy.py']
            for name in names:(scripts/name).write_text('unit fixture '+name)
            report=dict(passed=True,checks=[dict(passed=True)],bundle='bundle',
                        bundle_manifest_sha256=promotion.digest((bundle/'manifest.json').read_bytes()),
                        pfd_policy_code=policy_provenance(root),proofs={})
            for field,name in [('checker_sha256','check_release.py'),('staged_gate_sha256','staged_release.py'),
                               ('native_gate_sha256','dll_native_evidence.py'),('candidate_rtl_gate_sha256','verify_candidate_rtl.py')]:
                report[field]=promotion.digest((scripts/name).read_bytes())
            for name in promotion.PROOFS:
                path=root/(name+'.json');path.write_text('{}')
                report['proofs'][name]=dict(path=path.name,sha256=promotion.digest(path.read_bytes()))
            with patch.object(promotion,'ROOT',root):
                self.assertIn('--bundle',promotion.report_arguments(bundle,report))
                (scripts/'pfd_fast_reset_policy.py').write_text('changed topology validator')
                with self.assertRaisesRegex(ValueError,'current, passing staged release'):
                    promotion.report_arguments(bundle,report)

    def test_extra_missing_or_duplicate_lef_pins_are_rejected(self):
        text='MACRO dll\n  PIN CLK\n  PIN VSS\nEND dll\n'
        promotion.check_lef_interface('dll',text,['CLK','VSS'])
        for changed in [text.replace('  PIN VSS\n',''),text.replace('END dll','  PIN ERR\nEND dll'),
                        text.replace('END dll','  PIN CLK\nEND dll')]:
            with self.assertRaisesRegex(ValueError,'LEF interface'):
                promotion.check_lef_interface('dll',changed,['CLK','VSS'])

    def test_sealing_preserves_binary_bytes_and_rejects_a_changed_existing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            data=b'\x00exact tested library\xff\n';files={'electrical/full.spice':dict(data=data,source='source',sha256=promotion.digest(data))}
            root=Path(directory);target,stamp=promotion.seal(files,{'fixture':'unit test'},root)
            self.assertEqual((target/'electrical/full.spice').read_bytes(),data)
            self.assertEqual(promotion.seal(files,{'fixture':'unit test'},root),(target,stamp))
            self.assertFalse((root/'current.json').exists())
            (target/'electrical/full.spice').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'release file changed'):
                promotion.seal(files,{'fixture':'unit test'},root)

    def test_failed_copy_never_publishes_a_package_or_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);files={'electrical/full.spice':dict(data=b'actual',source='source',sha256='wrong')}
            with self.assertRaisesRegex(ValueError,'copy changed'):promotion.seal(files,{},root)
            self.assertEqual(list((root/'packages').iterdir()),[])
            self.assertFalse((root/'current.json').exists())

    def test_failed_gate_does_not_replace_the_previous_current_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'build/diagnostics/phy_candidate/rejected';(bundle/'release').mkdir(parents=True)
            (bundle/'release/status.json').write_text('{"passed":false,"checks":[]}')
            release=root/'build/release';release.mkdir();pointer=release/'current.json';pointer.write_bytes(b'previous pointer')
            with patch.object(promotion,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'passing staged release'):promotion.promote(bundle)
            self.assertEqual(pointer.read_bytes(),b'previous pointer')
            self.assertFalse((release/'packages').exists())

    def test_empty_or_partly_failed_checklists_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'bundle'
            with patch.object(promotion,'ROOT',root):
                for checks in [[],[{'passed':False}],[{'passed':True},{'passed':False}]]:
                    with self.assertRaisesRegex(ValueError,'passing staged release'):
                        promotion.report_arguments(bundle,dict(passed=True,checks=checks))

    def test_saved_success_cannot_bypass_mandatory_reanalysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'build/diagnostics/phy_candidate/fixture';(bundle/'release').mkdir(parents=True)
            (bundle/'release/status.json').write_text('{"passed":true}')
            release=root/'build/release';release.mkdir();pointer=release/'current.json';pointer.write_bytes(b'previous pointer')
            with patch.object(promotion,'ROOT',root),patch.object(promotion,'report_arguments',return_value=[]),\
                 patch.object(promotion.subprocess,'run',side_effect=RuntimeError('mandatory reanalysis failed')) as recheck:
                with self.assertRaisesRegex(RuntimeError,'mandatory reanalysis'):promotion.promote(bundle)
                recheck.assert_called_once()
            self.assertEqual(pointer.read_bytes(),b'previous pointer')
            self.assertFalse((release/'packages').exists())


class SelectedRXPackage(unittest.TestCase):
    def test_selected_rx_uses_its_own_gds_run_and_extraction(self):
        from promote_phy_candidate import digital_artifacts
        identity=dict(tx='build/diagnostics/tx',rx='build/diagnostics/rx')
        native=dict(pfd='build/diagnostics/pfd')
        name,physical,extraction=digital_artifacts(identity,native)[2]
        self.assertEqual(name,'openlvds_ddr_rx')
        self.assertEqual(extraction,physical/'extraction.json')
        self.assertTrue(str(physical).endswith('/build/diagnostics/rx'))
        baseline=digital_artifacts(dict(tx=identity['tx']),native)[2]
        self.assertTrue(str(baseline[1]).endswith('/build/physical/rx'))
        self.assertTrue(str(baseline[2]).endswith('/build/extracted/digital.json'))


class PoweredDigitalHandoff(unittest.TestCase):
    logical='''module rx (clk,data);
 input clk;
 output [1:0] data;
 wire n;
 assign n = clk;
 sky130_fd_sc_hd__buf_4 driver0 (.A(n),.X(data[0]));
 sky130_fd_sc_hd__buf_4 driver1 (.A(clk),.X(data[1]));
 sky130_fd_sc_hd__tapvpwrvgnd_1 tap ();
endmodule
'''
    powered='''module rx (clk,data,VPWR,VGND);
 input clk;
 output [1:0] data;
 inout VPWR;
 inout VGND;
 wire n;
 assign n = clk;
 sky130_fd_sc_hd__buf_4 driver0 (.A(n),.X(data[0]),.VPWR(VPWR),.VGND(VGND),.VPB(VPWR),.VNB(VGND));
 sky130_fd_sc_hd__buf_4 driver1 (.A(clk),.X(data[1]),.VPWR(VPWR),.VGND(VGND),.VPB(VPWR),.VNB(VGND));
 sky130_fd_sc_hd__tapvpwrvgnd_1 tap (.VPWR(VPWR),.VGND(VGND));
endmodule
'''
    ports=['clk','data[0]','data[1]','VPWR','VGND']

    def check(self,powered):promotion.check_powered_netlist('rx',powered,self.logical,self.ports)

    def test_powered_netlist_keeps_bus_ports_tap_rails_and_logic(self):
        self.check(self.powered)
        self.check(self.powered.replace('.A(n),.X(data[0])','.X(data[0]),.A(n)'))

    def test_swapped_missing_and_unconnected_power_connections_are_rejected(self):
        for changed in [self.powered.replace('.VNB(VGND)','.VNB(VPWR)',1),
                        self.powered.replace('.VPB(VPWR),','',1),
                        self.powered.replace('.VPWR(VPWR)','.VPWR(other)',1),
                        self.powered.replace('.VGND(VGND)','.VGND()',1),
                        self.powered.replace('tap (.VPWR(VPWR)','tap (.VNB(VGND),.VPWR(VPWR)')]:
            with self.assertRaises(ValueError):self.check(changed)

    def test_logic_drive_strength_or_continuous_assignment_changes_are_rejected(self):
        for changed in [self.powered.replace('.X(data[0])','.X(data[1])',1),
                        self.powered.replace('__buf_4','__buf_1',1),
                        self.powered.replace('assign n = clk','assign n = ~clk')]:
            with self.assertRaisesRegex(ValueError,'connectivity'):self.check(changed)

    def test_changed_port_width_direction_or_duplicate_cell_cannot_be_delivered(self):
        for changed in [self.powered.replace('[1:0]','[2:0]'),
                        self.powered.replace('input clk','output clk'),
                        self.powered.replace('driver1 (','driver0 ('),
                        self.powered.replace('inout VGND;','output VGND;')]:
            with self.assertRaises(ValueError):self.check(changed)

    def test_preflight_writes_only_an_unqualified_report_and_preserves_current(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'bundle';bundle.mkdir()
            q=root/'qualification';q.mkdir();(q/'manifest.json').write_text(json.dumps(dict(identity=dict(full_models=dict(pfd='pfd')))))
            identity=dict(qualification='qualification',tx='tx',rx='rx')
            (bundle/'manifest.json').write_text(json.dumps(dict(identity=identity)))
            for macro,folder in [('openlvds_tx_core','tx'),('lvds_pfd','pfd'),('openlvds_ddr_rx','rx')]:
                physical=root/folder;physical.mkdir();run=physical/'run'
                for kind,suffix,text in [('nl','nl',self.logical),('pnl','pnl',self.powered)]:
                    out=run/'final'/kind;out.mkdir(parents=True)
                    (out/(macro+'.'+suffix+'.v')).write_text(text.replace('module rx (','module '+macro+' ('))
                (physical/'summary.json').write_text(json.dumps(dict(run=str(run.relative_to(root)))))
                (physical/'extraction.json').write_text(json.dumps(dict(ports=self.ports)))
            release=root/'build/release';release.mkdir(parents=True);pointer=release/'current.json';pointer.write_bytes(b'previous release')
            with patch.object(promotion,'ROOT',root),patch.object(promotion,'load'),patch('builtins.print'):
                report=promotion.check_netlists(bundle)
            self.assertTrue(report['passed']);self.assertFalse(report['qualified_phy'])
            self.assertEqual(len(report['macros']),3);self.assertTrue((bundle/'netlist_preflight.json').exists())
            self.assertEqual(pointer.read_bytes(),b'previous release');self.assertFalse((release/'packages').exists())
