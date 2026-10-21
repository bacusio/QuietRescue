import unittest,tempfile,hashlib,base64,threading,io
from pathlib import Path
from PIL import Image
from engine import *
from media import recover_photos

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.b=Path(self.tmp.name);self.src=self.b/'source.img';self.root=self.b/'job';self.root.mkdir()
        self.src.write_bytes(b'a'*BLOCK+b'b'*BLOCK);s=self.src.stat()
        save(self.root/'plan.json',dict(kind='file',source=str(self.src),size=s.st_size,mtime_ns=s.st_mtime_ns,sector=512,start=0,end=s.st_size,stage_bytes=s.st_size,guards=[]))
    def tearDown(self):self.tmp.cleanup()
    def reader(self,fail=None):
        src=self.src
        class Fake:
            def __init__(self,r):pass
            def read(self,a,n):
                if a==fail:raise TimeoutError('test timeout')
                with src.open('rb') as f:f.seek(a);b=f.read(n)
                return dict(data=base64.b64encode(b).decode(),seconds=.01)
            def close(self):pass
        return Fake
    def test_roundtrip(self):
        capture(self.root,threading.Event(),lambda x:None,self.reader());self.assertTrue(verify(self.root)['complete'])
        target=self.b/'restored.img';export_image(self.root,target);self.assertEqual(self.src.read_bytes(),target.read_bytes())
        before=records(self.root);capture(self.root,threading.Event(),lambda x:None,self.reader());self.assertEqual(before,records(self.root))
    def test_fault_no_retry(self):
        capture(self.root,threading.Event(),lambda x:None,self.reader(BLOCK));self.assertEqual(load(self.root/'status.json')['status'],'FAULT_STOP')
        self.assertFalse(verify(self.root)['complete']);before=records(self.root)
        capture(self.root,threading.Event(),lambda x:None,self.reader());self.assertEqual(before,records(self.root))
        with self.assertRaises(ValueError):export_image(self.root,self.b/'bad.img')
    def test_tamper(self):
        capture(self.root,threading.Event(),lambda x:None,self.reader());next(self.root.glob('chunk-*.bin')).write_bytes(b'bad')
        with self.assertRaises(ValueError):verify(self.root)
    def test_uncertain(self):
        append(self.root/'map.jsonl',dict(state='REQUESTED',offset=0,length=BLOCK))
        capture(self.root,threading.Event(),lambda x:None,self.reader());self.assertEqual(verify(self.root)['verified_bytes'],BLOCK)
    def test_recover_photo(self):
        im=Image.new('RGB',(160,120),'orange');buf=io.BytesIO();im.save(buf,format='JPEG');jpeg=buf.getvalue()
        self.src.write_bytes(jpeg+bytes(2*BLOCK-len(jpeg)));p=load(self.root/'plan.json');p['mtime_ns']=self.src.stat().st_mtime_ns;save(self.root/'plan.json',p)
        capture(self.root,threading.Event(),lambda x:None,self.reader());found=recover_photos(self.root);self.assertEqual(len(found),1);self.assertEqual(Path(found[0]['path']).read_bytes(),jpeg)
    def test_space_floor(self):
        from unittest.mock import patch
        from collections import namedtuple
        usage=namedtuple('usage','total used free')(FLOOR,FLOOR,0)
        with patch('engine.shutil.disk_usage',return_value=usage):capture(self.root,threading.Event(),lambda x:None,self.reader())
        self.assertEqual(records(self.root),[]);self.assertEqual(load(self.root/'status.json')['status'],'SPACE_LOW')
    def test_real_worker(self):
        capture(self.root,threading.Event(),lambda x:None)
        self.assertTrue(verify(self.root)['complete'])

    def test_resume_with_json_guards(self):
        # JSON guards are lists; persisted requests become tuples in capture.
        p=load(self.root/'plan.json');p['guards']=[[0,512]];save(self.root/'plan.json',p)
        append(self.root/'map.jsonl',dict(state='REQUESTED',offset=512,length=512))
        capture(self.root,threading.Event(),lambda x:None,self.reader())
        self.assertEqual(verify(self.root)['verified_bytes'],p['size']-1024)
        self.assertEqual(verify(self.root)['missing_ranges'],[(0,1024)])

if __name__=='__main__':unittest.main()
