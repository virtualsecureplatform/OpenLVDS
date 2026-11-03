import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import assemble_slew_dll as assembly
from spice_library import replace
from spice_probes import ProbeNetwork


class NativeSlewDLLAssembly(unittest.TestCase):
    def reference(self):
        return ('.subckt lvds_pfd REF FB RESET_N PD_ENABLE UP DN VDDD VSS\nXPHYS DN FB PD_ENABLE REF RESET_N UP VSS VDDD lvds_pfd_physical\n.ends lvds_pfd\n'
                '.subckt lvds_pfd_physical DN FB PD_ENABLE REF RESET_N UP VGND VPWR\nCOLD REF VGND 1f\n.ends lvds_pfd_physical\n'
                '.subckt lvds_bias PB NB VA VSS\nRBIAS PB NB 10\n.ends lvds_bias\n'
                '.subckt openlvds_dll_analog A B\nCKEEP A B 16p\n.ends openlvds_dll_analog\n')
    def native(self):
        return '.subckt lvds_pfd UP REF DN RESET_N FB PD_ENABLE VPWR VGND\nX0 UP delivered S VGND sky130_fd_pr__nfet_01v8 w=1 l=.15\nRKEEP REF delivered 20\n.ends lvds_pfd\n'
    def ports(self):return 'UP REF DN RESET_N FB PD_ENABLE VPWR VGND'.split()

    def test_only_pfd_definitions_change_and_actual_port_order_is_preserved(self):
        source=self.reference();model=assembly.compose(source,self.native(),self.ports())
        self.assertIn('XPHYS UP REF DN RESET_N FB PD_ENABLE VDDD VSS lvds_pfd_physical',model)
        self.assertIn('RKEEP REF delivered 20',model);self.assertNotIn('COLD',model)
        for name in ('lvds_bias','openlvds_dll_analog'):
            self.assertEqual(replace(source,name,'MASK').count('MASK'),1)
            self.assertIn(source[source.index('.subckt '+name):source.index('.ends '+name)+len('.ends '+name)],model)
        ProbeNetwork(model).validate('XP R F RST EN UP DN VD 0 lvds_pfd',['XP:XPHYS:delivered'])

    def test_missing_extra_duplicate_or_reordered_metadata_ports_fail(self):
        for ports in (self.ports()[:-1],self.ports()+['EXTRA'],self.ports()[:-1]+['VPWR'],list(reversed(self.ports()))):
            with self.assertRaises(ValueError):assembly.compose(self.reference(),self.native(),ports)

    def test_injected_definitions_and_wrong_public_wrapper_fail(self):
        for native in (self.native().replace('lvds_pfd','wrong_top'),self.native()+'.subckt extra A B\nR0 A B 1\n.ends extra\n'):
            with self.assertRaises(ValueError):assembly.compose(self.reference(),native,self.ports())
        with self.assertRaises(ValueError):assembly.compose(self.reference().replace('UP DN VDDD VSS\n','DN UP VDDD VSS\n',1),self.native(),self.ports())

    def test_failed_rc_gate_does_not_create_a_native_model(self):
        with tempfile.TemporaryDirectory() as d,patch.object(assembly.extraction,'verify',return_value={'passed':False}):
            root=Path(d)
            with self.assertRaises(ValueError):assembly.prepare(root/'rc',root/'q')
            self.assertEqual(list(root.iterdir()),[])

    def test_reference_and_bias_validator_use_scientific_interpreter_with_clean_paths(self):
        r=SimpleNamespace(returncode=0,stdout='{"references":1}',stderr='')
        with patch.dict(os.environ,{'PYTHONPATH':'wrong-nix-python','PYTHONHOME':'wrong'}),patch.object(assembly.subprocess,'run',return_value=r) as run:
            self.assertEqual(assembly.bias_count('model'),1)
            args,kw=run.call_args;self.assertEqual(args[0][0],'/usr/bin/python3');self.assertEqual(kw['input'],'model')
            self.assertNotIn('PYTHONPATH',kw['env']);self.assertNotIn('PYTHONHOME',kw['env'])
        with patch.object(assembly,'scientific',return_value={'references':2}),self.assertRaises(ValueError):assembly.bias_count('model')
