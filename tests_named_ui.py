"""Exercise the GUI handler with synthetic saved inputs and mocked dialogs."""
import queue,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from app import App
import tests_named_recovery as fixtures
class NamedUI(unittest.TestCase):
    def run_case(self,destination_serial):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as t:
            root=Path(t);index,record=fixtures.NamedTests().fixture(root)
            (root/'plan.json').write_text('{}');(root/'map.jsonl').write_text('')
            raw=root/'record.mft';raw.write_bytes(b'X'*1024)
            a=App.__new__(App);a.busy=False;a.stop=threading.Event();a.events=queue.Queue();messages=[]
            a.job=lambda fn,operation:messages.append(fn())
            with patch('app.filedialog.askopenfilename',return_value=str(raw)),patch('app.filedialog.askdirectory',return_value=str(root)),patch('app.simpledialog.askstring',side_effect=['0','512','synthetic geometry fixture']),patch('app.destination_identity',return_value={'serial':destination_serial}),patch('saved_ranges.SavedRanges',return_value=index),patch('named_recovery.parse',return_value=record):
                if destination_serial=='SYNTHETIC':
                    with self.assertRaises(ValueError):a.recover_named_record()
                    self.assertFalse((root/'Original.doc').exists())
                else:
                    a.recover_named_record();self.assertEqual((root/'Original.doc').read_bytes(),b'B'*512+b'A'*188)
                    self.assertIn('Original.doc',messages[0])
    def test_callback_exports_saved_fragments(self):self.run_case('DESTINATION')
    def test_source_disk_destination_rejected(self):self.run_case('SYNTHETIC')
    def test_cancel_has_no_job(self):
        a=App.__new__(App);a.busy=False
        a.job=lambda *args,**kwargs:self.fail('Unexpected job')
        with patch('app.filedialog.askopenfilename',return_value=''):a.recover_named_record()
if __name__=='__main__':unittest.main()
