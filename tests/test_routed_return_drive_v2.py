# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_routed_return_drive_v2 as pilot
import verify_routed_return_drive_v2 as verification

BANK='''.subckt openlvds_weighted_bank_physical_v2 IN OUT VPWR VGND
R1 IN forward0.B 1
R2 OUT turn0.Y 1
Xn OUT IN VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15
Xd OUT VGND sky130_fd_pr__diode_pw2nd_05v5 area=1
.ends
'''
PAIR='''.subckt openlvds_nand2b_4_o1_stack_guard_pair_v2 A_N B Y VGND VPWR
R1 Y private 1
Xn private B VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15
Xc private VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2
.ends
'''
DEVICE=dict(name='XD:Xn',model='sky130_fd_pr__nfet_01v8',limit_v=1.95,terminals=['OUT','IN','0','0'])


class RoutedReturnDriveTests(unittest.TestCase):
    def test_addition_retains_every_original_byte_device_and_private_boost_node(self):
        for spec in pilot.specifications():
            text,devices,count=pilot.augment(BANK,PAIR,spec,[DEVICE])
            rows=text.splitlines();added=[r+'\n' for r in rows if r.startswith('XBOOST')]
            recovered=text[:-len(PAIR)]
            for row in added:recovered=recovered.replace(row,'',1)
            self.assertEqual(recovered,BANK);self.assertTrue(text.endswith(PAIR))
            self.assertEqual(count,1);self.assertEqual(devices[0],DEVICE)
            self.assertEqual(devices[1]['terminals'],['XD:XBOOST:private','IN','0','0'])
            self.assertEqual(devices[1]['name'],'XD:XBOOST:Xn')
            self.assertEqual('XBOOST_SHUNT' in text,spec['shunt_um']==2)
        aliases='node "turn0.Y" 0 0\nequiv "turn0.A_N" "forward0.B"\nequiv "turn0.B" "IN"\n'
        pilot.check_anchors(BANK,aliases)
        with self.assertRaises(ValueError):pilot.check_anchors(BANK,aliases.replace('"IN"','"OUT"'))
        with self.assertRaises(ValueError):pilot.augment(BANK,PAIR.replace('A_N B Y','A B Y'),pilot.specifications()[0],[DEVICE])

    def test_source_and_options_are_retained_except_title_and_explicit_short_stop(self):
        spec=dict(variant='guarded',coarse=0,codes=pilot.original.CODES,process='ss',temperature=40,
                  input_slew_ps=100,control_slew_ps=20,load_ff=20)
        witness=dict(ports=['IN','OUT','VPWR','VGND'],devices=[DEVICE],controls=[])
        with patch.dict('os.environ',{'PDK_ROOT':'/fixture/pdk'}):
            old=pilot.original.fixture(Path('/fixture'),spec,witness);new=pilot.fixture(Path('/fixture'),spec,witness)
        self.assertEqual(new,old.replace('OpenLVDS '+pilot.original.VERSION,'OpenLVDS '+pilot.VERSION,1).replace('.tran 2p 60n 0 2p','.tran 2p 8n 0 2p',1))
        self.assertIn('tanh((time-52.1n)',new);self.assertIn('.options itl4=100',new)

    def test_first_pulse_keeps_voltage_and_headroom_gates_separate(self):
        t=np.linspace(0,8e-9,4001);width=100e-12/(2*np.arctanh(.8))
        def pulse(shift):return .9*(np.tanh((t-2.1e-9-shift)/width)-np.tanh((t-6.1e-9-shift)/width))
        names=['time','v(in)','v(out)',*[f'v(b{i})' for i in range(5)],*[f'v(c{i})' for i in range(15)]]
        w=np.column_stack([t,pulse(0),pulse(500e-12),*([np.zeros(len(t))]*20)])
        good=pilot.analyze(names,w,dict(devices=[DEVICE]));self.assertTrue(good['first_pulse_diagnostic_passed'])
        self.assertAlmostEqual(good['minimum_quarter_headroom_ps'],1e6/410/4-500,places=5)
        unsafe=w.copy();unsafe[1500,2]=2.0
        result=pilot.analyze(names,unsafe,dict(devices=[DEVICE]));self.assertFalse(result['terminal_screen_passed']);self.assertFalse(result['first_pulse_diagnostic_passed'])
        slow=w.copy();slow[:,2]=pulse(700e-12)
        result=pilot.analyze(names,slow,dict(devices=[DEVICE]));self.assertTrue(result['terminal_screen_passed']);self.assertFalse(result['first_pulse_diagnostic_passed'])
        self.assertFalse(result['electrical_qualification_passed']);self.assertFalse(result['qualified_phy'])
        shifted=np.column_stack([w,np.full(len(w),.2)])
        witness=dict(devices=[DEVICE],controls=[dict(kind='fine',bit=0,nodes=['INTERNAL'])])
        result=pilot.analyze(names+['v(internal)'],shifted,witness)
        self.assertFalse(result['routed_control_settling_passed']);self.assertFalse(result['first_pulse_diagnostic_passed'])

    def test_an_incomplete_trace_cannot_become_an_eight_ns_diagnostic_pass(self):
        t=np.linspace(0,8e-9,4001);width=100e-12/(2*np.arctanh(.8))
        def pulse(shift):return .9*(np.tanh((t-2.1e-9-shift)/width)-np.tanh((t-6.1e-9-shift)/width))
        names=['time','v(in)','v(out)',*[f'v(b{i})' for i in range(5)],*[f'v(c{i})' for i in range(15)]]
        data=np.column_stack([t,pulse(0),pulse(500e-12),*([np.zeros(len(t))]*20)])
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            def write_raw(rows):
                header=('Title: fixture\nPlotname: Transient Analysis\nFlags: real\n'
                        f'No. Variables: {len(names)}\nNo. Points: {len(rows)}\nVariables:\n'+
                        ''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n')
                (folder/'bench.raw').write_bytes(header.encode()+np.asarray(rows,dtype='<f8').tobytes())
            write_raw(data)
            result=pilot.measure(folder,pilot.specifications()[0],dict(devices=[DEVICE],controls=[]))
            self.assertTrue(result['first_pulse_diagnostic_passed']);self.assertEqual(result['completed_diagnostic_ns'],8)
            write_raw(data[t<=7.5e-9])
            with self.assertRaises(ValueError):pilot.measure(folder,pilot.specifications()[0],dict(devices=[DEVICE],controls=[]))
