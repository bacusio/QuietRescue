import hashlib,json,tempfile,threading,unittest
from pathlib import Path
from saved_ranges import SavedRanges
class CleanupImportTests(unittest.TestCase):
    def fixture(self,root):
        job=root/'job';job.mkdir();recovered=root/'recovered';recovered.mkdir()
        original=job/'chunk.bin';body=b'original saved block';video=recovered/'movie.mkv';video.write_bytes(b'header'+body+b'other')
        (job/'plan.json').write_text(json.dumps(dict(serial='FIXTURE',size=100000)))
        (job/'map.jsonl').write_text(json.dumps(dict(state='GOOD',offset=512,length=len(body),file_offset=0,file=str(original),sha256=hashlib.sha256(body).hexdigest()))+'\n')
        entry=dict(path=str(original),bytes=len(body),video_offset=6,reconstruction_video=str(video),video_sha256=hashlib.sha256(video.read_bytes()).hexdigest())
        ledger=recovered/'lossless-cleanup-ledger.json';ledger.write_text(json.dumps(dict(status='COMPLETE',files=[entry])))
        return job,recovered,ledger,video,body
    def test_exact_reconstruction_without_recreating_original(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            root=Path(t);job,recovered,ledger,video,body=self.fixture(root)
            index=SavedRanges([job],[ledger],recovered)
            index.export(512,len(body),root/'output.dat',threading.Event())
            self.assertEqual((root/'output.dat').read_bytes(),body);self.assertFalse((job/'chunk.bin').exists())
    def test_container_tamper_even_outside_selected_block(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            job,recovered,ledger,video,body=self.fixture(Path(t));video.write_bytes(video.read_bytes()[:-1]+b'X')
            index=SavedRanges([job],[ledger],recovered)
            with self.assertRaisesRegex(ValueError,'movie hash mismatch'):index.export(512,len(body),Path(t)/'output.dat',threading.Event())
            self.assertFalse((Path(t)/'output.dat').exists())
    def test_missing_without_ledger_remains_missing(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            job,recovered,ledger,video,body=self.fixture(Path(t))
            with self.assertRaisesRegex(ValueError,'Missing saved bytes'):SavedRanges([job]).parts(512,len(body))
    def test_unfinished_ledger_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            job,recovered,ledger,video,body=self.fixture(Path(t));j=json.loads(ledger.read_text());j['status']='DELETING_VERIFIED_DUPLICATES';ledger.write_text(json.dumps(j))
            with self.assertRaises(ValueError):SavedRanges([job],[ledger],recovered)
    def test_replacement_outside_selected_root_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            root=Path(t);job,recovered,ledger,video,body=self.fixture(root);outside=root/'other.mkv';outside.write_bytes(video.read_bytes());j=json.loads(ledger.read_text());j['files'][0]['reconstruction_video']=str(outside);ledger.write_text(json.dumps(j))
            with self.assertRaises(ValueError):SavedRanges([job],[ledger],recovered)
if __name__=='__main__':unittest.main()
