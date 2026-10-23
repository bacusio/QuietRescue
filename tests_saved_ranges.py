import hashlib,json,tempfile,threading,unittest
from pathlib import Path
from saved_ranges import SavedRanges
from mapped_videos import discover
from mapped_videos import recover
from unittest.mock import patch
from container_headers import mkv_length
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.root=Path(self.tmp.name);self.stop=threading.Event()
        self.movie=b'\x1aE\xdf\xa3\x8b\x42\x82\x88matroska'+b'\x18\x53\x80\x67\x85abcde'
    def tearDown(self):self.tmp.cleanup()
    def job(self,name,data,offset,serial='TEST'):
        p=self.root/name;p.mkdir();(p/'chunk.bin').write_bytes(data)
        (p/'plan.json').write_text(json.dumps(dict(kind='disk',serial=serial,size=100000)))
        (p/'map.jsonl').write_text(json.dumps(dict(state='GOOD',offset=offset,length=len(data),file='chunk.bin',file_offset=0,sha256=hashlib.sha256(data).hexdigest()))+'\n')
        return p
    def test_header_split_between_jobs_and_exact_export(self):
        a=self.job('a',b'padding'+self.movie[:2],100);b=self.job('b',self.movie[2:]+b'end',109)
        index=SavedRanges([a,b]);found=discover(index,self.stop)
        self.assertEqual(len(found),1);self.assertTrue(found[0]['saved_coverage_complete']);self.assertEqual(found[0]['start_byte'],107)
        target=self.root/'restored.mkv';r=index.export(107,len(self.movie),target,self.stop)
        self.assertEqual(target.read_bytes(),self.movie);self.assertEqual(r['source_disk_reads'],0)
    def test_gap_refused_before_output(self):
        index=SavedRanges([self.job('a',b'ab',100),self.job('b',b'cd',103)])
        with self.assertRaises(ValueError):index.export(100,5,self.root/'missing.mkv',self.stop)
        self.assertFalse((self.root/'missing.mkv.partial').exists())
    def test_other_disk_refused(self):
        with self.assertRaises(ValueError):SavedRanges([self.job('a',b'a',100),self.job('b',b'b',101,'OTHER')])
    def test_changed_saved_file_refused(self):
        a=self.job('a',b'abcd',100);index=SavedRanges([a]);(a/'chunk.bin').write_bytes(b'bad')
        with self.assertRaises(ValueError):index.export(100,4,self.root/'bad.mkv',self.stop)
    def test_conflicting_overlap_refused(self):
        with self.assertRaises(ValueError):SavedRanges([self.job('a',b'ab',100),self.job('b',b'cd',101)])
    def test_unknown_length_not_guessed(self):
        self.assertIsNone(mkv_length(self.movie[:20]+b'\xffabcde')['declared_bytes'])
    def test_duplicate_mapping_deduplicated(self):
        index=SavedRanges([self.job('a',b'ab',100),self.job('b',b'ab',100)])
        self.assertEqual(len(index.rows),1)
    def test_cancel_during_verification(self):
        index=SavedRanges([self.job('a',b'ab',100)]);self.stop.set()
        with self.assertRaises(RuntimeError):index.export(100,2,self.root/'cancel.mkv',self.stop)
    def test_resume_skips_export_of_complete_movie(self):
        a=self.job('a',self.movie,100)
        first=recover([a],self.root,self.stop)
        with patch.object(SavedRanges,'export',side_effect=AssertionError('Must not export again')):
            second=recover([a],self.root,self.stop)
        self.assertEqual(first['output'],second['output']);self.assertEqual(len(second['outputs']),1)
    def test_resume_detects_changed_output(self):
        a=self.job('a',self.movie,100);first=recover([a],self.root,self.stop)
        Path(first['outputs'][0]['path']).write_bytes(b'tampered')
        with self.assertRaises(ValueError):recover([a],self.root,self.stop)
    def test_resume_does_not_recreate_moved_movie(self):
        a=self.job('a',self.movie,100);first=recover([a],self.root,self.stop)
        Path(first['outputs'][0]['path']).rename(self.root/'moved.mkv')
        with self.assertRaises(ValueError):recover([a],self.root,self.stop)
    def interrupted(self):
        a=self.job('a',b'abcdefgh',100);target=self.root/'resume.mkv'
        def pause(info):
            if info['copied_bytes']>=3:self.stop.set()
        with patch('saved_ranges.BUFFER',3):
            with self.assertRaisesRegex(RuntimeError,'Stopped'):
                SavedRanges([a]).export(100,8,target,self.stop,pause)
        self.stop.clear()
        return a,target,target.with_suffix('.mkv.partial'),target.with_suffix('.mkv.partial.checkpoint.json')
    def test_resume_authenticated_prefix_and_uncheckpointed_tail(self):
        a,target,part,checkpoint=self.interrupted()
        self.assertEqual(part.read_bytes(),b'abc')
        with part.open('ab') as stream:stream.write(b'uncommitted')
        with patch('saved_ranges.BUFFER',3):
            result=SavedRanges([a]).export(100,8,target,self.stop)
        self.assertEqual(target.read_bytes(),b'abcdefgh')
        self.assertEqual(result['sha256'],hashlib.sha256(b'abcdefgh').hexdigest())
        self.assertFalse(part.exists());self.assertFalse(checkpoint.exists())
    def test_resume_refuses_modified_prefix_without_truncation(self):
        a,target,part,checkpoint=self.interrupted()
        part.write_bytes(b'XbcEXTRA')
        with self.assertRaisesRegex(ValueError,'prefix changed'):
            SavedRanges([a]).export(100,8,target,self.stop)
        self.assertEqual(part.read_bytes(),b'XbcEXTRA')
    def test_resume_refuses_changed_input_binding(self):
        a,target,part,checkpoint=self.interrupted()
        (a/'chunk.bin').write_bytes(b'abcDefgh')
        with self.assertRaises(ValueError):SavedRanges([a]).export(100,8,target,self.stop)
        self.assertEqual(part.read_bytes(),b'abc')
    def test_unknown_partial_is_not_overwritten(self):
        a=self.job('a',b'abcdefgh',100);target=self.root/'unknown.mkv';part=target.with_suffix('.mkv.partial')
        part.write_bytes(b'private data')
        with self.assertRaises(FileExistsError):SavedRanges([a]).export(100,8,target,self.stop)
        self.assertEqual(part.read_bytes(),b'private data')
    def test_short_checkpointed_prefix_is_refused(self):
        a,target,part,checkpoint=self.interrupted()
        part.write_bytes(b'ab')
        with self.assertRaisesRegex(ValueError,'shorter than checkpoint'):
            SavedRanges([a]).export(100,8,target,self.stop)
    def test_resume_across_saved_block_boundary(self):
        a=self.job('a',b'abc',100);b=self.job('b',b'defgh',103);target=self.root/'joined.mkv'
        def pause(info):
            if info['copied_bytes']==3:self.stop.set()
        with self.assertRaisesRegex(RuntimeError,'Stopped'):
            SavedRanges([a,b]).export(100,8,target,self.stop,pause)
        self.stop.clear()
        result=SavedRanges([a,b]).export(100,8,target,self.stop)
        self.assertEqual(target.read_bytes(),b'abcdefgh')
        self.assertEqual(len(result['spans']),2)
    def test_recover_resumes_interrupted_export_without_rebuilding_complete_output(self):
        a=self.job('a',self.movie,100);export_progress=[]
        def pause(info):
            if info['status']=='EXPORTING_VERIFIED_RANGE':
                export_progress.append(info['copied_bytes']);self.stop.set()
        with patch('saved_ranges.BUFFER',5):
            with self.assertRaisesRegex(RuntimeError,'Stopped'):
                recover([a],self.root,self.stop,pause)
        self.assertTrue(export_progress)
        self.stop.clear()
        with patch('saved_ranges.BUFFER',5):
            result=recover([a],self.root,self.stop)
        movie=Path(result['outputs'][0]['path'])
        self.assertEqual(movie.read_bytes(),self.movie)
        self.assertEqual(result['outputs'][0]['sha256'],hashlib.sha256(self.movie).hexdigest())
        with patch.object(SavedRanges,'export',side_effect=AssertionError('Completed output rebuilt')):
            again=recover([a],self.root,self.stop)
        self.assertEqual(again['outputs'][0]['path'],str(movie))
    def test_resume_after_receipt_saved_before_final_rename(self):
        a=self.job('a',b'abcdefgh',100);target=self.root/'rename.mkv'
        original_rename=Path.rename
        def interrupt_rename(path,destination):
            if path.name=='rename.mkv.partial':raise RuntimeError('Simulated interruption')
            return original_rename(path,destination)
        with patch.object(Path,'rename',interrupt_rename):
            with self.assertRaisesRegex(RuntimeError,'Simulated interruption'):
                SavedRanges([a]).export(100,8,target,self.stop)
        self.assertTrue(target.with_suffix('.mkv.json').exists())
        result=SavedRanges([a]).export(100,8,target,self.stop)
        self.assertEqual(target.read_bytes(),b'abcdefgh')
        self.assertEqual(result['bytes'],8)
if __name__=='__main__':unittest.main()
