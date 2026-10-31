# SPDX-License-Identifier: GPL-3.0-only
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from spice_slots import slot,reserved_slots
from qualify_dll_candidate import screen_task


class Slots(unittest.TestCase):
    def test_frozen_aperture_reservation_limits_new_workers_to_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/'build/characterization/rx_aperture/e9ca7d2f2ae6d61b/state.json'
            state.parent.mkdir(parents=True);state.write_text(json.dumps(dict(status='running')))
            mutex=threading.Lock();active=0;peak=0
            def work(_):
                nonlocal active,peak
                with slot(root):
                    with mutex:active+=1;peak=max(peak,active)
                    time.sleep(.04)
                    with mutex:active-=1
            with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(work,range(6)))
            self.assertLessEqual(peak,2)
            state.write_text(json.dumps(dict(status='complete')))
            self.assertEqual(reserved_slots(root),0)

    def test_bulk_tests_are_not_part_of_the_early_screen(self):
        self.assertTrue(screen_task(dict(id='loop_ss_0')))
        self.assertTrue(screen_task(dict(id='phase_ff_0_-150ps')))
        self.assertFalse(screen_task(dict(id='loop_sf_40')))
        self.assertFalse(screen_task(dict(id='clock_390_0.45')))
