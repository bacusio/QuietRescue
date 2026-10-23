import json,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from partition_scan import analyze,TESTDISK_SHA,FLOOR
from image_recovery import sha

class StagingTests(unittest.TestCase):
    def test_cancel_before_access(self):
        stop=threading.Event();stop.set()
        with patch('partition_scan.Path',side_effect=AssertionError('Unexpected access')):
            with self.assertRaisesRegex(RuntimeError,'before image access'):
                analyze('unused','unused',stop)
    def case(self,free,cancel_during_copy=False):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            root=Path(t).resolve();source=root/'source.bin';source.write_bytes(b'A'*(9*1024**2))
            before=sha(source);stop=threading.Event()
            def path(p):
                if Path(p)==source:raise ValueError('No short path')
                return str(p)
            def digest(p):return TESTDISK_SHA if Path(p).name=='testdisk_win.exe' else sha(p)
            def progress(info):
                if cancel_during_copy:stop.set()
            with patch('partition_scan.find_photorec',return_value=root/'photorec_win.exe'),patch('partition_scan.sha',side_effect=digest),patch('partition_scan.ascii_path',side_effect=path),patch('partition_scan.shutil.disk_usage',return_value=SimpleNamespace(free=free)),patch('partition_scan.subprocess.Popen') as spawn:
                with self.assertRaises(RuntimeError):analyze(source,root,stop,progress)
                spawn.assert_not_called()
            job=next(root.glob('PartitionScan-*'));state=json.loads((job/'analysis.json').read_text(encoding='utf-8'))
            self.assertEqual(state['status'],'STOPPED_ERROR');self.assertFalse(state.get('staged_input_verified',False))
            self.assertFalse((job/'input.img').exists());self.assertEqual(sha(source),before)
            if cancel_during_copy:self.assertTrue((job/'input.partial').exists())
    def test_low_space_never_launches(self):self.case(FLOOR)
    def test_mid_copy_cancel_retains_partial_not_img(self):self.case(FLOOR+100*1024**2,True)

if __name__=='__main__':unittest.main()
