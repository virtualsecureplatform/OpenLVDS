# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import release_io_300 as release

ROOT=Path(__file__).resolve().parents[1]
REQ=json.loads((ROOT/'io_300.json').read_text())['requirements']


class ReleaseIo300(unittest.TestCase):
    def test_judges_cover_exactly_the_policy_gates(self):
        policy=json.loads((ROOT/'qualification_io_300.json').read_text())
        self.assertEqual(set(policy['gates']),set(release.GATES))
        self.assertEqual(set(policy['macros']),set(release.MACROS))

    def test_missing_evidence_is_a_failed_check_not_an_exception(self):
        with tempfile.TemporaryDirectory() as folder, patch.multiple(release,BENCH=Path(folder)/'bench',RELEASE=Path(folder)/'release'):
            for gate,judge in release.GATES.items():
                e=release.Evidence();judge(e)
                self.assertTrue(e.checks,gate)
                self.assertFalse(all(e.checks.values()),gate)

    def test_case_rejects_stale_failed_or_foreign_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);out=base/'driver_tt_25';out.mkdir()
            (out/'bench.cir.prn').write_text('wave')
            good=dict(passed=True,requirements_sha256='c',contract='io_300.json',simulation_scope_sha256='s',simulator='xyce',
                      waveform_sha256=release.sha(out/'bench.cir.prn'))
            def judge(**change):
                (out/'summary.json').write_text(json.dumps({**good,**change}))
                with patch.object(release,'rel',lambda p:str(p)):
                    return release.case(release.Evidence(),base,'driver_tt_25','c',dict(driver='s'))
            self.assertTrue(judge()['passed'])
            for change in [dict(passed=False),dict(requirements_sha256='other'),dict(simulation_scope_sha256='old'),
                           dict(simulator='ngspice'),dict(waveform_sha256='0'),dict(contract='requirements.json')]:
                with self.assertRaises(ValueError,msg=change):judge(**change)

    def test_receiver_liberty_has_measured_arcs_and_supplies(self):
        timing=dict(input_pin_capacitance_pf=.08,input_transition_20_80_ps=[260.,388.6,517.2],output_load_ff=[10,50,100,200],
            **{k:[[.2+.01*i+.02*j for j in range(4)] for i in range(3)] for k in ['cell_rise','cell_fall','rise_transition','fall_transition']})
        text=release.liberty('openlvds_io_rx','ss',40,REQ,dict(width_um=220.,height_um=220.),timing)
        self.assertEqual(text.count('{'),text.count('}'))
        for needle in ['library (openlvds_io_rx_ss_040C)','cell (openlvds_io_rx)','related_pin : "INP"','cell_rise (rx_delay)',
                       'fall_transition (rx_delay)','voltage_map (VDDIO, 3.3)','pg_pin (VSS)','index_1 ("0.26000, 0.38860, 0.51720")',
                       'index_2 ("0.01000, 0.05000, 0.10000, 0.20000")','area : 48400.000','"0.20000, 0.22000, 0.24000, 0.26000"']:
            self.assertIn(needle,text)

    def test_driver_liberty_has_no_timing_arc_on_analog_outputs(self):
        text=release.liberty('openlvds_io_tx','tt',25,REQ,dict(width_um=440.,height_um=455.),dict(input_capacitance_pf=.031))
        self.assertNotIn('timing ()',text);self.assertIn('pin (D) { direction : input; capacitance : 0.03100;',text)
        self.assertIn('pin (OUTP) { direction : inout;',text);self.assertEqual(text.count('{'),text.count('}'))

    def test_extractions_compare_by_circuit_not_by_numbering(self):
        base='.subckt m A B VSS\nX0 A.t1 B.t0 VSS.t3 VSS.t2 sky130_fd_pr__nfet_01v8 w=1 l=0.15\nR0 A.t1 A.n0 1.5\nR1 A A.n0 2.5\nC0 A B 1.2345f\nC1 A VSS 2.1422f\n.ends\n'
        renumbered='.subckt m A B VSS\nC1 VSS A 2.14221f\nR1 A.n7 A 2.5\nX9 A.t4 B.t2 VSS.t0 VSS.t1 sky130_fd_pr__nfet_01v8 l=0.15 w=1\nR0 A.n7 A.t4 1.5\nC0 B A 1.2345f\n.ends\n'
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a.spice';b=Path(folder)/'b.spice';a.write_text(base)
            def compare(text):
                b.write_text(text);return release.netlists_equivalent(a,b)
            same=compare(renumbered)
            self.assertTrue(same['equivalent'],same);self.assertEqual((same['devices'],same['resistors'],same['capacitors']),(1,2,2))
            self.assertFalse(compare(renumbered.replace('2.5','2.6'))['equivalent'])           # resistor value
            self.assertFalse(compare(renumbered.replace('C0 B A','C0 B VSS'))['equivalent'])   # capacitor moved
            self.assertFalse(compare(renumbered.replace('w=1','w=2'))['equivalent'])           # device size
            self.assertFalse(compare(renumbered.replace('B.t2','A.t4'))['equivalent'])         # device rewired
            self.assertFalse(compare(renumbered.replace('R1 A.n7 A 2.5\n',''))['equivalent']) # element missing

    def test_schematic_closure_is_self_contained(self):
        for macro,inner in [('openlvds_io_tx','openlvds_driver_core'),('openlvds_io_rx','openlvds_receiver_core')]:
            text=release.schematic_closure(macro)
            defined=set(__import__('re').findall(r'(?im)^\.subckt\s+(\S+)',text))
            self.assertIn(macro,defined);self.assertIn(inner,defined);self.assertIn('lvds_bias',defined)
            self.assertNotIn('openlvds_dll_analog',defined)
            # Every instantiated subcircuit is defined before the top that uses it.
            self.assertLess(text.index('.subckt lvds_bias'),text.index('.subckt '+macro))

    def test_fresh_extraction_leaves_the_checked_extraction_untouched(self):
        import types
        net='.subckt {m} A\nR0 A B 1\nC0 B 0 1f\n.ends\n'
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);designs={}
            for macro in release.MACROS:
                out=base/'build/extracted/abc'/macro;out.mkdir(parents=True)
                (out/(macro+'.rcx.spice')).write_text(net.format(m=macro));(out/'other.txt').write_text('checked')
                designs[macro]=dict(raw_netlist=str((out/(macro+'.rcx.spice')).relative_to(base)))
                (base/(macro+'.gds')).write_text('gds')
            (base/'build/extracted/current.json').write_text(json.dumps(dict(designs=designs)))
            (base/'build/layout').mkdir();(base/'build/release').mkdir()
            (base/'build/layout/current.json').write_text(json.dumps(dict(source_sha256='s',
                designs={m:dict(ports={},lvs_source_sha256='l') for m in release.MACROS})))
            (base/'build/release/views.json').write_text(json.dumps({m:dict(gds=dict(path=m+'.gds')) for m in release.MACROS}))
            def extract(macro,gds,*_):
                out=base/'build/extracted/abc'/macro
                (out/(macro+'.rcx.spice')).write_text(net.format(m=macro).replace('R0 A B','R7 A B'));(out/'other.txt').write_text('fresh')
                return dict(passed=True,gds_sha256='g',raw_netlist=designs[macro]['raw_netlist'])
            with patch.multiple(release,ROOT=base,RELEASE=base/'build/release',netlists_equivalent=lambda a,b:dict(equivalent=True)), \
                 patch.dict(sys.modules,extract=types.SimpleNamespace(extract=extract)):
                self.assertEqual(release.fresh_rc(),0)
                result=json.loads((base/'build/release/fresh_rc.json').read_text())
                for macro in release.MACROS:
                    out=base/'build/extracted/abc'/macro
                    self.assertIn('R0 A B',(out/(macro+'.rcx.spice')).read_text())
                    self.assertEqual((out/'other.txt').read_text(),'checked')
                    self.assertFalse(out.with_name(macro+'.checked').exists())
                    self.assertIn('R7 A B',(base/result[macro]['fresh']).read_text())
                    self.assertTrue(result[macro]['comparison']['equivalent'])

    def test_raw_rc_comparison_expects_the_unreduced_netlist_scope(self):
        asked=[]
        def scopes(extracted=True,raw=False):
            asked.append((extracted,raw));return dict(driver='d',receiver='r',link='l')
        with tempfile.TemporaryDirectory() as folder, patch.multiple(release,BENCH=Path(folder),expected_scopes=scopes):
            release.gate_exact_rc_equivalence(release.Evidence())
        self.assertEqual(asked,[(True,False),(True,True)])


if __name__=='__main__':unittest.main()
