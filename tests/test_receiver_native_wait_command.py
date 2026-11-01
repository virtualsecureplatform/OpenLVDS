# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from continue_receiver_tail_headroom import replay_command


class NativeReceiverWaitCommand(unittest.TestCase):
    def test_default_native_command_is_preserved(self):
        self.assertEqual(replay_command(Path('build/replay'),[]),[
            '--ngspice','python3','scripts/probe_receiver_tail_headroom_candidate.py','run','build/replay'])

    def test_selected_kernel_wait_is_explicit_and_inside_existing_budget(self):
        self.assertEqual(replay_command(Path('build/replay'),[4]),[
            '--ngspice','python3','scripts/run_spice_wait_slot.py','receiver-native','build/replay','--wait-slot','4'])
        for slots in [[6],[-1],[True]]:
            with self.assertRaises(ValueError):replay_command(Path('build/replay'),slots)


if __name__=='__main__':unittest.main()
