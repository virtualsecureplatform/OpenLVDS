# SPDX-License-Identifier: GPL-3.0-only
import json,re,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_selected_receiver as replay

class SelectedReceiverReplay(unittest.TestCase):
    def test_every_recorded_timestamp_and_voltage_roundtrips_without_resampling(self):
        wave=np.zeros((3,len(replay.NAMES)+2));wave[:,1]=[0,1.2345678901234567e-11,1.88049e-7]
        headers={'V('+n+')':i+2 for i,n in enumerate(replay.NAMES)}
        for i,n in enumerate(replay.NAMES):wave[:,i+2]=[.12345678901234567+i,.5+i,1.2+i]
        rows=replay.recorded_sources(wave,headers).splitlines();self.assertEqual(len(rows),len(replay.RECORDED))
        for name,row in zip(replay.RECORDED,rows):
            points=np.array(list(map(float,re.search(r'PWL\((.*)\)',row)[1].split()))).reshape(-1,2)
            np.testing.assert_array_equal(points[:,0],wave[:,1]);np.testing.assert_array_equal(points[:,1],wave[:,headers['V('+name+')']])
        self.assertFalse(any(row.startswith('VREC_RXCLOCK ') for row in rows))

    def test_fixture_retains_actual_native_receiver_and_bias_but_removes_transmitter(self):
        parent='\n'.join(['.lib "pdk/sky130.lib.spice" ss','.options device temp=40','.options timeint method=gear',
            'VIO VDDIO 0 3.3','VDIG VDDD 0 1.8','VREF VREF 0 1.2','VRST RESET_N 0 PWL(0 0 2n 1.8)','IREF_RX IREF_RX 0 35u',
            'XBR IREF_RX NBR VDDIO 0 lvds_bias','XDR RP RN RXDATA VREF IREF_RX NBR VDDIO VDDD 0 openlvds_receiver_core',
            'XCR RCP RCN RXCLOCK VREF IREF_RX NBR VDDIO VDDD 0 openlvds_receiver_core',
            'XRX 0 VDDD RXCLOCK Q0 Q1 RESET_N RXDATA RXVALID openlvds_ddr_rx','CQ0 Q0 0 20f','CQ1 Q1 0 20f',
            'XTX ignored transmitter'])
        deck=replay.fixture(parent,Path('/case'),188.049e-9)
        self.assertIn('XRX 0 VDDD RXCLOCK Q0 Q1 RESET_N RXDATA RXVALID openlvds_ddr_rx',deck)
        self.assertIn('.tran 5p',deck);self.assertNotIn('XTX',deck)
        with self.assertRaisesRegex(ValueError,'fixture row'):replay.fixture(parent.replace('3.3','3.2'),Path('/case'),188e-9)

    def test_calibration_rejects_excess_crossing_error(self):
        t=np.linspace(0,10e-9,1001);parent=np.zeros((len(t),8));parent[:,1]=t
        parent[:,6]=.9+.9*np.sin(2*np.pi*(t/2e-9-.1));parent[:,7]=.9+.9*np.sin(2*np.pi*(t/2.5e-9-.1))
        self.assertTrue(replay.agreement(parent,parent,1e-9,9e-9)['passed'])
        shifted=parent.copy();shifted[:,1]+=100e-12
        self.assertFalse(replay.agreement(parent,shifted,1e-9,9e-9)['passed'])

    def test_unrelated_calibration_cannot_admit_changed_architecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);control=root/'control';control.mkdir()
            (control/'manifest.json').write_text(json.dumps(dict(identity=dict(variant='lvt',parent='other'))))
            (control/'summary.json').write_text(json.dumps(dict(control_calibrated=True)))
            with patch.object(replay,'ROOT',root),patch.object(replay,'run') as run:
                with self.assertRaisesRegex(ValueError,'calibrate'):replay.control_proofs(control,root/'chosen')
                run.assert_not_called()

    def test_partial_replay_is_retained_without_a_new_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'build/diagnostics/selected_receiver_replay/control';out.mkdir(parents=True)
            (out/'manifest.json').write_text(json.dumps(dict(identity=dict(simulator_provenance='runtime',code={},inputs={}),files={})))
            (out/'bench.raw').write_bytes(b'partial')
            with patch.object(replay,'ROOT',root),patch.object(replay,'provenance',return_value='runtime'),patch.object(replay,'lease') as lease,patch.object(replay.subprocess,'run') as run:
                with self.assertRaisesRegex(ValueError,'Partial receiver replay'):replay.run(out)
                lease.assert_not_called();run.assert_not_called()
            self.assertEqual((out/'bench.raw').read_bytes(),b'partial')

if __name__=='__main__':unittest.main()
