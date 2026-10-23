import tempfile,unittest
from pathlib import Path
from image_recovery import require_scan_finished

class CompletionTests(unittest.TestCase):
    def test_remaining_session_rejects_success_without_modification(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            p=Path(t)/'photorec.ses';p.write_bytes(b'#123\ncheckpoint')
            with self.assertRaises(RuntimeError):require_scan_finished(t)
            self.assertEqual(p.read_bytes(),b'#123\ncheckpoint')
    def test_empty_session_is_ambiguous_not_success(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            (Path(t)/'photorec.ses').touch()
            with self.assertRaises(RuntimeError):require_scan_finished(t)
    def test_removed_session_passes_completion_gate(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            require_scan_finished(t)

if __name__=='__main__':unittest.main()
