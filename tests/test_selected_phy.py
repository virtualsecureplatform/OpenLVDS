# SPDX-License-Identifier: GPL-3.0-only
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import selected_phy as selected
from spice_scope import closure_hash

class SelectedPhy(unittest.TestCase):
    def circuits(self):
        return ''.join('.subckt '+n+' A B\nR0 A B '+str(i+1)+'\n.ends '+n+'\n'
            for i,n in enumerate(sorted(selected.BLOCKS|set(selected.PROTECTED))))

    def test_both_selected_analog_closures_are_installed_and_all_other_blocks_preserved(self):
        base=self.circuits();driver='.subckt openlvds_driver_core A B\nR1 A B 21\n.ends openlvds_driver_core\n'
        rx='.subckt openlvds_receiver_core A B\nR1 A B 31\n.ends openlvds_receiver_core\n'
        actual=selected.overlay(base,driver,rx)
        self.assertEqual(closure_hash(actual,selected.DRIVER),closure_hash(driver,selected.DRIVER))
        self.assertEqual(closure_hash(actual,selected.RECEIVER),closure_hash(rx,selected.RECEIVER))
        for top in selected.PROTECTED:self.assertEqual(closure_hash(actual,top),closure_hash(base,top))
        with self.assertRaisesRegex(ValueError,'terminal order'):selected.overlay(base,driver,rx.replace('core A B','core B A'))

    def fixture(self,root):
        (root/'requirements.json').write_text('{}\n');(root/'proof').write_text('physical proof')
        text=self.circuits();inputs={n:'hash-'+n for n in selected.BLOCKS}
        info=dict(inputs=inputs,digital_models={},blocks={n:dict(model_sha256=inputs[n],closure_sha256=closure_hash(text,n),artifact='selected') for n in selected.BLOCKS},
            physical_reports={'proof':selected.digest(root/'proof')},code={})
        paths=[root/'build/diagnostics'/n for n in ['dll','tx','rx','comparison','receiver']]
        with patch.object(selected,'ROOT',root),patch.object(selected,'assemble',return_value=(text,info)):
            out=selected.prepare(*paths)
        return out,text,info

    def test_shared_stage_and_loader_reconstruct_the_same_exact_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out,text,info=self.fixture(root)
            with patch.object(selected,'ROOT',root),patch.object(selected,'assemble',return_value=(text,info)) as rebuild:
                data,inputs,models=selected.load(out)
                self.assertEqual(data,text.encode());self.assertEqual(inputs,info['inputs']);self.assertEqual(models,{})
                rebuild.assert_called_once()
                with self.assertRaisesRegex(ValueError,'certified approximate'):selected.load(out,True)

    def test_changed_library_or_physical_evidence_is_rejected(self):
        for target in ['full.spice','proof']:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);out,text,info=self.fixture(root)
                path=out/target if target=='full.spice' else root/target;path.write_text(path.read_text()+'changed')
                with patch.object(selected,'ROOT',root),patch.object(selected,'assemble',return_value=(text,info)):
                    with self.assertRaises(ValueError):selected.load(out)

    def test_a_different_reconstructed_selection_cannot_load_even_with_unchanged_file_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out,text,info=self.fixture(root);changed=copy.deepcopy(info)
            changed['blocks'][selected.RECEIVER]['model_sha256']='other'
            with patch.object(selected,'ROOT',root),patch.object(selected,'assemble',return_value=(text,changed)):
                with self.assertRaisesRegex(ValueError,'explicit block selection'):selected.load(out)

    def test_diagnostic_capture_cannot_be_promoted_by_editing_manifest_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out,text,info=self.fixture(root);path=out/'manifest.json';manifest=json.loads(path.read_text());manifest['qualified']=True;path.write_text(json.dumps(manifest))
            with patch.object(selected,'ROOT',root),patch.object(selected,'assemble') as rebuild:
                with self.assertRaisesRegex(ValueError,'diagnostic'):selected.load(out)
                rebuild.assert_not_called()

if __name__=='__main__':unittest.main()
