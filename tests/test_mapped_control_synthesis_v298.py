# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('yosys'),'Use scripts/env.sh with Yosys')
class MappedControlSynthesisTests(unittest.TestCase):
    def check(self,top,parameters,widths):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'control.json'
            files=' '.join(str(p) for p in sorted((ROOT/'rtl/v2').glob('*.v')))
            args=' '.join('-set '+name+' '+str(value) for name,value in parameters.items())
            script=f'read_verilog {files}; chparam {args} {top}; hierarchy -top {top}; proc; opt; check -assert; write_json {output}'
            result=subprocess.run(['yosys','-Q','-T','-p',script],capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            module=json.loads(output.read_text())['modules'][top]
            for name,width in widths.items():self.assertEqual(len(module['ports'][name]['bits']),width,name)
            self.assertTrue(module['cells'])

    def test_tx_keeps_legal_and_native_bus_widths_distinct(self):
        self.check('openlvds_tx_control_v3',dict(CODE_WIDTH=2,RAW_WIDTH=4,CODE_COUNT=3,NATIVE_CODE_COUNT=16,
            TABLE_MODEL_ADMITTED=1,DLL_MODEL_ADMITTED=1,DCC_MODEL_ADMITTED=1,RAW_CODES="12'h925"),
            dict(codes=8,raw_indices=8,raw_codes=16))

    def test_rx_keeps_independent_dll_and_deskew_native_buses(self):
        self.check('openlvds_rx_control_v3',dict(DLL_CODE_WIDTH=2,DLL_RAW_WIDTH=4,DLL_CODE_COUNT=3,DLL_NATIVE_CODE_COUNT=16,
            DESKEW_CODE_WIDTH=2,DESKEW_RAW_WIDTH=4,DESKEW_CODE_COUNT=3,DESKEW_NATIVE_CODE_COUNT=16,
            DLL_TABLE_MODEL_ADMITTED=1,DESKEW_TABLE_MODEL_ADMITTED=1,DLL_RAW_CODES="12'h925",DESKEW_RAW_CODES="12'h925",
            DLL_MODEL_ADMITTED=1,CODE_MODEL_ADMITTED=1,DESKEW_MODEL_ADMITTED=1,DCC_MODEL_ADMITTED=1),
            dict(codes=8,raw_indices=8,raw_codes=16,deskew_index=2,native_deskew_code=4))

if __name__=='__main__':unittest.main()
