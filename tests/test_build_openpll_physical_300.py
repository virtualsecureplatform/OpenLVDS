import io,json,sys,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_openpll_physical_300 as p
class Physical300Tests(unittest.TestCase):
    def test_wrong_pin_never_runs_physical_tools(self):
        with patch.object(p.subprocess,'check_output',return_value='wrong'),patch.object(p.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'pin mismatch'):p.run()
            run.assert_not_called()
    def test_failed_flow_is_retained_without_extraction_or_admission(self):
        profile=p.load();pin=profile['requirements']['openpll_commit'];blob=io.BytesIO()
        with tarfile.open(fileobj=blob,mode='w') as t:
            info=tarfile.TarInfo('README');info.size=3;t.addfile(info,io.BytesIO(b'old'))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'clocking_300mhz.json').write_text(json.dumps(profile))
            result=type('Result',(),{'returncode':3,'check_returncode':lambda self:(_ for _ in ()).throw(RuntimeError('flow failed'))})()
            with patch.object(p,'ROOT',root),patch.object(p.subprocess,'check_output',side_effect=[pin,blob.getvalue()]),patch.object(p.subprocess,'run',return_value=result) as run,patch.dict(p.os.environ,{'PDK_ROOT':'/pdk'}):
                with self.assertRaisesRegex(RuntimeError,'flow failed'):p.run()
                self.assertEqual(run.call_count,1)
            folder=next((root/'build/diagnostics/openpll_physical_300').iterdir())
            self.assertEqual(json.loads((folder/'state.json').read_text())['status'],'failed')
            self.assertFalse((folder/'summary.json').exists())
            self.assertEqual((folder/'source/README').read_text(),'old')
