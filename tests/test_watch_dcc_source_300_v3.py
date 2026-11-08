# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import watch_dcc_source_300_v3 as p


class ContainerChildTests(unittest.TestCase):
    def test_child_can_execute_in_the_actual_parent_environment(self):
        result=p.subprocess.run(p.replay_command(['--help'],False),cwd=p.ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('--full',result.stdout)
        self.assertEqual(p.replay_command(['234','235'],False)[-2:],['234','235'])

    def test_full_child_selects_only_full_remeasurement(self):
        command=p.replay_command([],True)
        self.assertEqual(command[0],sys.executable)
        self.assertEqual(command[-1],'--full')
        self.assertFalse(any('env.sh' in part or part=='apptainer' for part in command))
