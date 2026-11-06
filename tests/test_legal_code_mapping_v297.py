# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import export_proposed_code_rom_v297 as p
ROOT=p.ROOT

import test_proposed_code_rom_v297 as fixtures

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Use scripts/env.sh')
class NativeCodeMappingRtlTests(unittest.TestCase):
    def run_tb(self,top,**overrides):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'tb.vvp';args=['iverilog','-g2012','-Wall','-s',top,'-o',str(binary)]
            args += ['-P'+top+'.'+k+'='+str(v) for k,v in overrides.items()]
            args += [str(f) for f in sorted((ROOT/'rtl/v2').glob('*.v'))]+[str(ROOT/'tb'/f'{top}.v')]
            result=subprocess.run(args,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertIn('PASS',result.stdout)

    def test_lookup_bounds_admission_unknown_index_and_four_section_validity(self):self.run_tb('tb_legal_code_map_v2')
    def test_actual_calibration_and_cdc_use_reverse_native_mapping(self):self.run_tb('tb_dll_control_v3')
    def test_unadmitted_table_cannot_launch_or_lock(self):self.run_tb('tb_dll_control_v3',TABLE_ADMITTED=0)
    def test_unadmitted_detector_cannot_launch_or_lock(self):self.run_tb('tb_dll_control_v3',ADMITTED=0)
    def test_mapping_does_not_bypass_exact_physical_settling(self):self.run_tb('tb_dll_control_v3',HOLD_SETTLE=1)

    def test_exported_word_width_and_order_drive_the_rtl_lookup_exactly(self):
        fixtures.ProposedRomExportTests.setUpClass();r=p.parameters(fixtures.ProposedRomExportTests.selection)
        checks='\n'.join(f"index={k};#1;if(!valid || raw_code!=={r['RAW_WIDTH']}'d{code})$fatal(1,\"Exported entry {k} differs\");" for k,code in enumerate(r['codes']))
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);tb=base/'tb.v';binary=base/'tb.vvp'
            tb.write_text(f'''module exported_rom_tb;
reg [{r['CODE_WIDTH']-1}:0] index=0;
wire [{r['RAW_WIDTH']-1}:0] raw_code;wire valid;
openlvds_legal_code_map_v2 #(.INDEX_WIDTH({r['CODE_WIDTH']}),.RAW_WIDTH({r['RAW_WIDTH']}),.CODE_COUNT({r['CODE_COUNT']}),
.NATIVE_CODE_COUNT({r['NATIVE_CODE_COUNT']}),.MODEL_ADMITTED(1),.RAW_CODES({r['RAW_CODES']})) dut(index,raw_code,valid);
initial begin {checks}
$display("PASS exported native ROM");$finish;end
endmodule
''')
            result=subprocess.run(['iverilog','-g2012','-s','exported_rom_tb','-o',str(binary),str(ROOT/'rtl/v2/openlvds_legal_code_map_v2.v'),str(tb)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertIn('PASS',result.stdout)

    @unittest.skipUnless(shutil.which('yosys'),'Yosys required')
    def test_mapping_synthesizes_without_latches_or_clocked_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'map.json'
            script=f"read_verilog {ROOT/'rtl/v2/openlvds_legal_code_map_v2.v'}; chparam -set INDEX_WIDTH 2 -set RAW_WIDTH 4 -set CODE_COUNT 3 -set NATIVE_CODE_COUNT 10 -set MODEL_ADMITTED 1 -set RAW_CODES 12'h925 openlvds_dll_code_map_v2; hierarchy -top openlvds_dll_code_map_v2; flatten; proc; opt; check -assert; write_json {output}"
            result=subprocess.run(['yosys','-Q','-T','-p',script],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            module=json.loads(output.read_text())['modules']['openlvds_dll_code_map_v2']
            self.assertTrue(module['cells'])
            self.assertTrue(all('dff' not in c['type'].lower() and 'latch' not in c['type'].lower() for c in module['cells'].values()))

if __name__=='__main__':unittest.main()
