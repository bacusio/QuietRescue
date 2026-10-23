import io
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from document_validation import validate_document, OLE_MAGIC


CONTENT = b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
RELS = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
WORD = b'<document xmlns="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><body/></document>'


def make_ole():
    sector = 512
    header = bytearray(sector)
    header[:8] = OLE_MAGIC
    header[28:30] = b'\xfe\xff'
    struct.pack_into('<HH', header, 30, 9, 6)
    struct.pack_into('<II', header, 44, 1, 0)
    struct.pack_into('<109I', header, 76, 17, *([0xFFFFFFFF] * 108))
    directory = bytearray(sector)

    def entry(index, name, start, size):
        offset = index * 128
        raw = (name + '\0').encode('utf-16le')
        directory[offset:offset + len(raw)] = raw
        struct.pack_into('<H', directory, offset + 64, len(raw))
        directory[offset + 66] = 2
        struct.pack_into('<I', directory, offset + 116, start)
        struct.pack_into('<Q', directory, offset + 120, size)

    entry(1, 'WordDocument', 1, 4096)
    entry(2, '0Table', 9, 4096)
    word = bytearray(4096)
    word[:2] = b'\xec\xa5'
    fat = [0xFFFFFFFE] + list(range(2, 9)) + [0xFFFFFFFE] + list(range(10, 17)) + [0xFFFFFFFE, 0xFFFFFFFD]
    fat.extend([0xFFFFFFFF] * (128 - len(fat)))
    return bytes(header + directory + word + bytes(4096) + struct.pack('<128I', *fat))


class DocumentValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def office(self, name='saved.docx', parts=None):
        p = self.root / name
        with zipfile.ZipFile(p, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for key, value in (parts or {'[Content_Types].xml': CONTENT,
                                         '_rels/.rels': RELS,
                                         'word/document.xml': WORD}).items():
                z.writestr(key, value)
        return p

    def test_docx_crc_and_required_xml(self):
        result = validate_document(self.office())
        self.assertEqual(result['validation'], 'ZIP_CRC_AND_REQUIRED_XML_PASS')
        self.assertFalse(result['original_file_complete_proven'])

    def test_xlsx_and_pptx_required_parts(self):
        for kind, part, tag, mime in (
            ('xlsx', 'xl/workbook.xml', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'),
            ('pptx', 'ppt/presentation.xml', 'http://schemas.openxmlformats.org/presentationml/2006/main',
             'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml'),
        ):
            types = (f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     f'<Override PartName="/{part}" ContentType="{mime}"/></Types>').encode()
            rels = RELS.replace(b'word/document.xml', part.encode())
            body = (f'<{"workbook" if kind == "xlsx" else "presentation"} xmlns="{tag}"/>').encode()
            p = self.office('saved.' + kind, {'[Content_Types].xml': types,
                                             '_rels/.rels': rels, part: body})
            self.assertEqual(validate_document(p)['validation'], 'ZIP_CRC_AND_REQUIRED_XML_PASS')

    def test_docx_rejects_crc_corruption(self):
        p = self.office()
        data = p.read_bytes().replace(b'word/document.xml', b'word/document.xml')
        # Flip compressed payload while preserving central directory.
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info = z.getinfo('word/document.xml')
        offset = info.header_offset + 30 + len(info.filename) + len(info.extra)
        damaged = bytearray(data)
        damaged[offset + 2] ^= 1
        p.write_bytes(damaged)
        self.assertEqual(validate_document(p)['validation'], 'STRUCTURE_FAILED')

    def test_docx_rejects_xml_entities(self):
        evil = b'<!DOCTYPE document [<!ENTITY x SYSTEM "file:///secret">]><document xmlns="urn:test"/>'
        p = self.office(parts={'[Content_Types].xml': CONTENT, '_rels/.rels': RELS,
                               'word/document.xml': evil})
        self.assertEqual(validate_document(p)['validation'], 'STRUCTURE_FAILED')

    def test_docx_rejects_utf16_dtd(self):
        evil = ('<?xml version="1.0" encoding="UTF-16"?>'
                '<!DOCTYPE document [<!ENTITY x SYSTEM "file:///secret">]>'
                '<document xmlns="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>').encode('utf-16')
        p = self.office(parts={'[Content_Types].xml': CONTENT, '_rels/.rels': RELS,
                               'word/document.xml': evil})
        self.assertEqual(validate_document(p)['validation'], 'STRUCTURE_FAILED')

    def test_docx_rejects_zip_bomb_before_decompression(self):
        p = self.office(parts={'[Content_Types].xml': CONTENT, '_rels/.rels': RELS,
                               'word/document.xml': WORD, 'padding': b'X' * (2 * 1024**2)})
        self.assertEqual(validate_document(p)['validation'], 'NOT_VALIDATED_LIMIT')

    def test_ole_word_streams_and_fib(self):
        p = self.root / 'saved.doc'
        p.write_bytes(make_ole())
        self.assertEqual(validate_document(p)['validation'], 'OLE_DIRECTORY_AND_WORD_FIB_PASS')
        data = bytearray(p.read_bytes())
        data[2 * 512:2 * 512 + 2] = b'XX'
        p.write_bytes(data)
        self.assertEqual(validate_document(p)['validation'], 'STRUCTURE_FAILED')

    def test_pdf_requires_structure_and_parser(self):
        p = self.root / 'saved.pdf'
        p.write_bytes(b'%PDF-1.4\nstartxref\n0\n%%EOF\n')
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.assertEqual(validate_document(p)['validation'], 'PDF_BOUNDARY_MARKERS_ONLY')
            return
        self.assertEqual(validate_document(p)['validation'], 'STRUCTURE_FAILED')
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        with p.open('wb') as out:
            writer.write(out)
        self.assertEqual(validate_document(p)['validation'], 'PDF_PAGE_TREE_PARSE_PASS')


if __name__ == '__main__':
    unittest.main()
