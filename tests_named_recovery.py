import hashlib,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from saved_ranges import SavedRanges
from named_recovery import recover_record,safe_name
class NamedTests(unittest.TestCase):
    def fixture(self,root):
        index=SavedRanges.__new__(SavedRanges);index.identity=('SYNTHETIC',4096);index.checked={};index.rows=[]
        for start,data in [(1024,b'A'*512),(2048,b'B'*512)]:
            p=root/str(start);p.write_bytes(data);st=p.stat()
            index.rows.append(dict(start=start,end=start+512,path=str(p),file_offset=0,sha256=hashlib.sha256(data).hexdigest(),stat=(st.st_size,st.st_mtime_ns)))
        record=dict(directory=False,has_attribute_list=False,names=[dict(name='Original.doc',namespace=1)],times={},streams=[dict(resident=False,unsupported_encoding=False,start_vcn=0,initialized_bytes=700,bytes=700,runs=[dict(vcn=0,lcn=4,clusters=1,sparse=False),dict(vcn=1,lcn=2,clusters=1,sparse=False)])])
        return index,record
    def test_fragmented_original_name(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as t:
            root=Path(t);index,record=self.fixture(root)
            with patch('named_recovery.parse',return_value=record):
                result=recover_record(index,b'fixture',0,512,'synthetic boot geometry',root,threading.Event())
            self.assertEqual((root/'Original.doc').read_bytes(),b'B'*512+b'A'*188)
            self.assertEqual(result['original_filename_from_mft'],'Original.doc')
            self.assertFalse(result['complete_original_file_proven'])
    def test_gap_rejected_before_output(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as t:
            root=Path(t);index,record=self.fixture(root);index.rows.pop()
            with patch('named_recovery.parse',return_value=record),self.assertRaises(ValueError):
                recover_record(index,b'fixture',0,512,'synthetic',root,threading.Event())
            self.assertFalse((root/'Original.doc.partial').exists())
    def test_unsafe_names_rejected(self):
        for name in ['../photo.jpg','CON.txt','file:stream','photo.jpg.']:
            with self.subTest(name=name),self.assertRaises(ValueError):safe_name([dict(name=name,namespace=1)])
if __name__=='__main__':unittest.main()
