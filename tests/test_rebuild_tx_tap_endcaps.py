# SPDX-License-Identifier: GPL-3.0-only
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import rebuild_tx_tap_endcaps as rebuild


class TapEndcapRebuild(unittest.TestCase):
    def test_only_declared_physical_cells_change(self):
        original=dict(DESIGN_NAME=rebuild.TOP,DECAP_CELLS=[],CLOCK_PERIOD=2.380952,VERILOG_FILES=['original.v'],STA_CORNERS=['nominal'])
        saved=copy.deepcopy(original);actual=rebuild.tap_config(original)
        self.assertEqual(original,saved)
        self.assertEqual({k:v for k,v in actual.items() if k not in ['ENDCAP_CELL','WELLTAP_CELL']},saved)
        self.assertEqual(actual['ENDCAP_CELL'],rebuild.TAP)
        self.assertEqual(actual['WELLTAP_CELL'],rebuild.TAP)
        with self.assertRaises(ValueError):rebuild.tap_config(dict(original,DECAP_CELLS=['decap']))

    def fixture(self):
        config=dict(ENDCAP_CELL=rebuild.TAP,WELLTAP_CELL=rebuild.TAP,DECAP_CELLS=[])
        powered=[];definition=[]
        for n in range(56):
            name=f'PHY_EDGE_ROW_{n}_Left_{n}'
            powered.append(f'{rebuild.TAP} {name} (.VPWR(VPWR),.VGND(VGND));')
            definition.append(f'- {name} {rebuild.TAP} + SOURCE DIST + FIXED ( 0 {n*2720} ) N ;')
        powered.append(f'{rebuild.TAP} TAP_TAPCELL_ROW_0_56 (.VPWR(VPWR),.VGND(VGND));')
        metrics={k:0 for k in ['magic__drc_error__count','klayout__drc_error__count','design__lvs_error__count',
            'design__disconnected_pin__count','design__critical_disconnected_pin__count','design__power_grid_violation__count']}
        for test in ['setup','hold']:
            metrics[f'timing__{test}__wns']=0
            for corner in ['nom','min','max']:metrics[f'timing__{test}__wns__corner:{corner}']=0
        return config,'paths','\n'.join(powered),'\n'.join(definition),metrics

    def test_boundary_welltap_power_physical_and_sta_all_required(self):
        args=self.fixture()
        with patch.object(rebuild,'tx_buffered_paths_retained',return_value=True):
            self.assertTrue(all(rebuild.physical_checks(*args).values()))
            for index,value in [(0,dict(args[0],ENDCAP_CELL='sky130_fd_sc_hd__decap_3')),
                                (2,args[2].replace('.VGND(VGND)','.VGND(VPWR)',1)),
                                (2,args[2].replace('TAP_TAPCELL_ROW_0_56','UNEXPECTED')),
                                (3,args[3].replace(rebuild.TAP,'sky130_fd_sc_hd__decap_3',1)),
                                (4,dict(args[4],magic__drc_error__count=1)),
                                (4,dict(args[4],timing__setup__wns=-.001)),(4,{})]:
                bad=list(args);bad[index]=value
                self.assertFalse(all(rebuild.physical_checks(*bad).values()))
        self.assertFalse(rebuild.physical_checks(*args)['functional_paths'])

    def test_failed_mapped_diagnostic_cannot_admit_physical_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'manifest.json').write_text('{}')
            for value in [False,None]:
                (p/'summary.json').write_text(json.dumps(dict(numerically_completed=value,returncode=1)))
                self.assertFalse(rebuild.causal_gate(p))

    def test_other_namespaces_are_rejected_before_any_flow(self):
        with self.assertRaises(ValueError):rebuild.build(Path('/tmp/retry'))
        with self.assertRaises(ValueError):rebuild.run(Path('/tmp/retry'))


if __name__=='__main__':unittest.main()
