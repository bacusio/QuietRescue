import struct,unittest
from ntfs_streams import parse
def record(name='DSC_0811.JPG',payload=b'photo',namespace=1):
    raw=bytearray(1024);raw[:4]=b'FILE'
    struct.pack_into('<HH',raw,4,48,3);struct.pack_into('<HH',raw,20,56,0)
    struct.pack_into('<I',raw,28,1024)
    pos=56
    for kind,value in [(0x30,bytes(64)+bytes([len(name),namespace])+name.encode('utf-16-le')),(0x80,payload)]:
        length=(24+len(value)+7)//8*8
        struct.pack_into('<II',raw,pos,kind,length)
        struct.pack_into('<IH',raw,pos+16,len(value),24)
        raw[pos+24:pos+24+len(value)]=value;pos+=length
    struct.pack_into('<I',raw,pos,0xffffffff);struct.pack_into('<I',raw,24,pos+8)
    raw[48:50]=b'XY'
    for i in (1,2):
        end=i*512-2;raw[48+i*2:50+i*2]=raw[end:end+2];raw[end:end+2]=b'XY'
    return bytes(raw)
class NamesTests(unittest.TestCase):
    def test_name_and_resident(self):
        j=parse(record());self.assertEqual(j['names'][0]['name'],'DSC_0811.JPG');self.assertTrue(j['deleted'])
        self.assertEqual(bytes.fromhex(j['streams'][0]['resident_hex']),b'photo')
    def test_unicode(self):self.assertEqual(parse(record('旅行照片.jpg'))['names'][0]['name'],'旅行照片.jpg')
    def test_fixup_inside_resident(self):
        data=bytes(range(256))*2
        self.assertEqual(bytes.fromhex(parse(record(payload=data))['streams'][0]['resident_hex']),data)
    def test_namespace_invalid(self):
        with self.assertRaises(ValueError):parse(record(namespace=9))
    def test_unsafe_name_is_metadata_not_path(self):
        self.assertEqual(parse(record('../evil.doc'))['names'][0]['name'],'../evil.doc')
if __name__=='__main__':unittest.main()
