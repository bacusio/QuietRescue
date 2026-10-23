import tempfile,threading,unittest,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from named_recovery import recover_record
from tests_ntfs_names import record
class ResidentTests(unittest.TestCase):
    def call(self,root,raw,stop=None):
        return recover_record(SimpleNamespace(),raw,0,512,'saved record fixture',root,stop or threading.Event())
    def test_fixups_and_original_unicode_filename(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            root=Path(t);data=bytes(range(256))*2;raw=record('旅行.txt',data)
            result=self.call(root,raw)
            self.assertEqual((root/'旅行.txt').read_bytes(),data)
            self.assertEqual(json.loads((root/'旅行.txt.mft.json').read_text(encoding='utf-8')),result)
            self.assertFalse(result['record_source_identity_proven'])
    def test_empty_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            self.call(Path(t),record('empty.txt',b''));self.assertEqual((Path(t)/'empty.txt').stat().st_size,0)
    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            root=Path(t);p=root/'photo.jpg';p.write_bytes(b'original')
            with self.assertRaises(FileExistsError):self.call(root,record('photo.jpg'))
            self.assertEqual(p.read_bytes(),b'original')
    def test_stop_before_output(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            event=threading.Event();event.set()
            with self.assertRaises(RuntimeError):self.call(Path(t),record(),event)
            self.assertFalse(list(Path(t).iterdir()))
    def test_space_reserve(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t,patch('named_recovery.shutil.disk_usage',return_value=SimpleNamespace(free=5_999_999_999)):
            with self.assertRaises(RuntimeError):self.call(Path(t),record())
            self.assertFalse(list(Path(t).iterdir()))
if __name__=='__main__':unittest.main()
