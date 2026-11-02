# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import recover_baseline_payload as recovery


class CompletedBaselineRecovery(unittest.TestCase):
    def trace(self,folder,raw,export=None):
        names=['time','v(xdr.co)','v(clk0)']
        header='Title: test\nFlags: real\nNo. Variables: 3\nNo. Points: '+str(len(raw))+'\nVariables:\n'
        header+=''.join(f'\t{i}\t{n}\tvoltage\n' for i,n in enumerate(names))+'Binary:\n'
        (folder/'bench.raw').write_bytes(header.encode()+raw.astype('<f8').tobytes())
        wave=np.column_stack([np.arange(len(raw)),raw]) if export is None else export
        np.savetxt(folder/'bench.cir.prn',wave,header='Index TIME V(XDR:CO) V(CLK0)',comments='',fmt='%.17g')

    def test_real_raw_reader_and_export_must_agree_for_all_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);raw=np.array([[0,0,.9],[6e-9,.2,1.8],[12e-9,.4,0]])
            self.trace(folder,raw);wave,headers=recovery.completed_export(folder,12)
            np.testing.assert_array_equal(wave[:,2:],raw[:,1:])
            self.assertEqual(headers['V(XDR:CO)'],2)

    def test_changed_export_voltage_time_or_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);raw=np.array([[0,0,.9],[6e-9,.2,1.8],[12e-9,.4,0]])
            for column in range(4):
                wave=np.column_stack([np.arange(3),raw]);wave[1,column]+=.001 if column!=1 else 1e-12
                self.trace(folder,raw,wave)
                with self.assertRaises(ValueError):recovery.completed_export(folder,12)

    def test_incomplete_or_nonfinite_raw_cannot_admit_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for raw in [np.array([[0,0,0],[11e-9,1,1]]),np.array([[0,0,0],[12e-9,np.nan,1]])]:
                self.trace(folder,raw)
                with self.assertRaisesRegex(ValueError,'Incomplete numerical'):recovery.completed_export(folder,12)

    def test_payload_uses_original_word_and_clock_analyzers(self):
        raw=np.column_stack([np.arange(16),np.arange(16)*1e-9,np.zeros((16,4))]);headers={'V(CLK0)':2,'V(RCP)':3,'V(RCN)':4,'V(RXCLOCK)':5}
        with patch.object(recovery,'completed_export',return_value=(raw,headers)) as reader,patch.object(recovery.original,'edge_times',return_value=np.arange(60,76)*1e-9),patch.object(recovery.original,'analyze',return_value={'decoded':True}) as analyze,patch.object(recovery.original,'pulse_transport',return_value={'edges':32}) as transport:
            self.assertEqual(recovery.payload_metrics(Path('/tmp/trace')),({'decoded':True},{'edges':32}))
            reader.assert_called_once_with(Path('/tmp/trace'),188.049)
            self.assertEqual(analyze.call_args.args[3],1000/410)
            self.assertEqual(transport.call_args.args[-2:],(60e-9,120e-9))

    def test_other_namespaces_are_rejected(self):
        with self.assertRaises(ValueError):recovery.prepare(Path('/tmp/other'))
        with self.assertRaises(ValueError):recovery.run(Path('/tmp/other'))


if __name__=='__main__':unittest.main()
