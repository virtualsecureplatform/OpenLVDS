# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_static_phase_clock_drive_v2 as pilot


class NativeClockDriveTests(unittest.TestCase):
    def test_exactly_one_native_clock_driver_is_added_without_changing_counter_or_loads(self):
        model=pilot.original.circuit.components.CLOCK_BUFFER
        old=f'.subckt harness RCLK CLK VPWR VGND\nXclock_driver RCLK CLK VGND VPWR {model}\nXcounter CLK q\nXload q Y load\n.ends harness\n'
        result=pilot.strengthen(old);extra=f'Xclock_driver_parallel RCLK CLK VGND VPWR {model}\n'
        self.assertEqual(result.replace(extra,''),old)
        for bad in [result,old.replace(model,'unknown_driver'),old.replace('RCLK CLK','OTHER CLK')]:
            with self.assertRaises(ValueError):pilot.strengthen(bad)

    def test_all_original_device_witnesses_and_distinct_private_copy_are_required(self):
        original=[dict(name='XD:Xclock_driver:X0',model='mos',terminals=['XD:Xclock_driver:n','CLK','VDD','0'],limit_v=1.95),
                  dict(name='XD:XR:X0',model='mos',terminals=['q','CLK','VDD','0'],limit_v=1.95)]
        clone=dict(original[0],name='XD:Xclock_driver_parallel:X0',terminals=['XD:Xclock_driver_parallel:n','CLK','VDD','0'])
        after=original+[clone];self.assertEqual(pilot.check_devices(original,after),1)
        bad_private=deepcopy(after);bad_private[-1]['terminals'][0]='XD:Xclock_driver:n'
        changed_limit=deepcopy(after);changed_limit[1]['limit_v']=2
        for bad in [after[1:],bad_private,changed_limit,after+[dict(clone,name='extra')]]:
            with self.assertRaises(ValueError):pilot.check_devices(original,bad)

    def test_duty_and_stopped_clock_regressions_keep_the_original_fixture_and_limits(self):
        specs=pilot.specifications()
        self.assertEqual([(s['duty'],s['stop_level']) for s in specs],[(.4,0),(.4,1),(.6,0),(.6,1)])
        for s in specs:
            self.assertEqual((s['process'],s['temperature'],s['mhz']),('ss',40,410))


if __name__=='__main__':unittest.main()
