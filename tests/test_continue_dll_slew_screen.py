import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_dll_slew_screen as f

class CalibrationJoin(unittest.TestCase):
 def test_live_owner_must_be_same_invocation(self):
  old={'MainPID':'12','InvocationID':'first'};live=dict(old,LoadState='loaded')
  self.assertFalse(f.terminal(old,live))
  for new in [dict(live,MainPID='13'),dict(live,InvocationID='other')]:
   with self.assertRaises(ValueError):f.terminal(old,new)
 def test_terminal_owner_failure_disappearance_or_restart_are_rejected(self):
  old={'MainPID':'12','InvocationID':'first'}
  done=dict(MainPID='0',InvocationID='first',LoadState='loaded',Result='success',ExecMainStatus='0')
  self.assertTrue(f.terminal(old,done))
  for new in [dict(done,Result='failed'),dict(done,ExecMainStatus='1'),dict(done,InvocationID='other'),dict(done,LoadState='not-found')]:
   with self.assertRaises(ValueError):f.terminal(old,new)
