# SPDX-License-Identifier: GPL-3.0-only
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import clocking_v2
import export_proposed_code_rom_v297 as exporter
import test_proposed_code_rom_v297 as fixtures
import json

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh')
class MappedControlTests(unittest.TestCase):
    def test_exported_rx_fragments_compile_with_independent_native_buses_and_no_admission(self):
        fixtures.ProposedRomExportTests.setUpClass()
        selections=dict(dll=fixtures.ProposedRomExportTests.selection,deskew=fixtures.ProposedRomExportTests.receiver_selection())
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            base=Path(tmp)
            for name,selection in selections.items():
                proposal=base/(name+'.json');proposal.write_text(json.dumps(selection));exporter.export(proposal,base/name,'rx_'+name)
            tb=base/'exported_rx.v';binary=base/'exported_rx.vvp'
            tb.write_text(f'''module exported_rx;
wire dll_valid,deskew_valid;wire [31:0] native_dll;wire [9:0] native_deskew;
openlvds_rx_control_v3 #(
`include "{base/'dll/parameters.vh'}"
,
`include "{base/'deskew/parameters.vh'}"
) dut(.mgmt_clk_25(1'b0),.reset_n(1'b0),.enable(1'b0),.dll_mapping_valid(dll_valid),
.deskew_mapping_valid(deskew_valid),.raw_codes(native_dll),.native_deskew_code(native_deskew));
initial begin #1;
if(dll_valid!==0 || deskew_valid!==0 || native_dll!==0 || native_deskew!==0)$fatal(1,"Proposal escaped unadmitted outputs");
$display("PASS v3 separate exported RX parameter tables");$finish;end
endmodule
''')
            build=subprocess.run(['iverilog','-g2012','-s','exported_rx','-o',str(binary),*map(str,sorted((ROOT/'rtl/v2').glob('*.v'))),str(tb)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertIn('PASS v3',run.stdout)

    def run_tb(self,top,**parameters):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'test.vvp'
            build=subprocess.run(['iverilog','-g2012','-Wall','-s',top,
                *['-P'+top+'.'+name+'='+str(value) for name,value in parameters.items()],'-o',str(binary),
                *map(str,sorted((ROOT/'rtl/v2').glob('*.v'))),str(ROOT/'sky130/v2/openlvds_dcc_clock_hold_v2.v'),
                str(ROOT/'tb/tb_dcc_release_v2.v'),str(ROOT/'tb'/f'{top}.v')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=240)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertIn('PASS v3',run.stdout)
            return run.stdout

    def test_tx_mapped_calibration_warmup_frame_payload_and_clock_loss(self):
        output=self.run_tb('tb_tx_control_v3');rows=re.findall(r'PAIR\s+(\d+) ([01]{2}) ([01])',output)
        self.assertEqual(len(rows),432);frame=''.join(map(str,clocking_v2.training_frame()))
        self.assertEqual(''.join(r[1] for r in rows),frame*3+format(clocking_v2.END_MARKER,'032b')+'10'*32)
        self.assertEqual([r[2] for r in rows],['0']*400+['1']*32)

    def test_tx_rejects_unadmitted_models_table_invalid_word_and_missing_settling(self):
        cases=[dict(DLL_ADMITTED=0),dict(DCC_ADMITTED=0),dict(TABLE_ADMITTED=0),dict(HOLD_SETTLE=1),dict(BAD_TABLE=1),
            *[dict(INVALID_POLICY=k) for k in (1,2,3)]]
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending=[pool.submit(self.run_tb,'tb_tx_control_v3',**case) for case in cases]
            for case,future in zip(cases,pending):
                with self.subTest(case=case):future.result()

    def test_rx_two_native_maps_acquisition_payload_retrain_faults_and_single_deadline(self):
        output=self.run_tb('tb_rx_control_v3',MODE=0);print(output,end='')
        match=re.search(r'DLL_LOCK age=\s*(\d+)',output);self.assertIsNotNone(match,output);lock_age=int(match.group(1))
        cases=[]
        for mode in range(1,15):
            parameters=dict(MODE=mode)
            if mode in (6,7,13):parameters['DEADLINE']=lock_age+(200 if mode==6 else 1000)
            if mode==14:parameters['DEADLINE']=200
            cases.append(parameters)
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending=[pool.submit(self.run_tb,'tb_rx_control_v3',**case) for case in cases]
            for case,future in zip(cases,pending):
                with self.subTest(case=case):print(future.result(),end='')

if __name__=='__main__':unittest.main()
