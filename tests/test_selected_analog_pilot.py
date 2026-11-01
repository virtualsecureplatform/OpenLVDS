from pathlib import Path
import json,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import selected_analog_pilot as pilot
from spice_scope import closure_hash

class EarlyAnalogPilot(unittest.TestCase):
 def test_overlay_preserves_unrelated_blocks_and_selects_both_cores(self):
  defs=lambda name:'.subckt '+name+' D G S B\nX0 D G S B sky130_fd_pr__nfet_01v8 w=1 l=0.15\n.ends '+name+'\n'
  base=''.join(defs(n) for n in pilot.PROTECTED+('openlvds_driver_core','openlvds_receiver_core'))
  driver=defs('openlvds_driver_core').replace('w=1','w=4')
  receiver=defs('openlvds_receiver_core').replace('nfet_01v8 ','nfet_01v8_lvt ')
  result=pilot.assemble(base,driver,receiver)
  for name in pilot.PROTECTED:self.assertEqual(closure_hash(base,name),closure_hash(result,name))
  self.assertEqual(closure_hash(driver,'openlvds_driver_core'),closure_hash(result,'openlvds_driver_core'))
  self.assertIn('nfet_01v8_lvt',result)
 def test_partial_run_cannot_restart_simulator(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(pilot,'ROOT',Path(tmp)),patch.object(pilot,'provenance',return_value='fixture'),patch.object(pilot.subprocess,'run') as run:
   root=Path(tmp)/'build/diagnostics/analog_link_pilot/example';root.mkdir(parents=True)
   (root/'manifest.json').write_text(json.dumps(dict(identity=dict(inputs={},code={},simulator_provenance='fixture'),files={})))
   (root/'bench.raw').write_bytes(b'partial')
   with self.assertRaisesRegex(ValueError,'Partial pilot'):pilot.run(root)
   run.assert_not_called();self.assertEqual((root/'bench.raw').read_bytes(),b'partial')
 def test_missing_receiver_result_refuses_before_any_source_run(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(pilot,'ROOT',Path(tmp)),patch.object(pilot,'engine',return_value='ngspice'),patch.object(pilot.receiver,'run') as run:
   root=Path(tmp)/'build'
   with self.assertRaisesRegex(ValueError,'Complete the receiver'):pilot.prepare(root/'link/example',root/'diagnostics/driver_native_restore/example',root/'diagnostics/receiver_lvt_pair_static/example')
   run.assert_not_called()
