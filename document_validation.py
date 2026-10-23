"""Bounded, read-only checks of already saved documents.

These checks describe the saved file, never prove that the source file was
fully recovered. No recovered filename or source metadata is inferred.
"""

from pathlib import Path
import struct
import zipfile
import zlib
import xml.etree.ElementTree as ET
from xml.parsers import expat


MAX_FILE = 2 * 1024**3
MAX_ZIP_MEMBERS = 10_000
MAX_ZIP_MEMBER = 128 * 1024**2
MAX_ZIP_TOTAL = 512 * 1024**2
MAX_XML = 8 * 1024**2
MAX_OLE_DIRECTORY = 8 * 1024**2
MAX_PDF_PARSE = 64 * 1024**2
OLE_MAGIC = bytes.fromhex('D0CF11E0A1B11AE1')
OFFICE = {
    'docx': ('word/document.xml', '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document',
             'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'),
    'xlsx': ('xl/workbook.xml', '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook',
             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'),
    'pptx': ('ppt/presentation.xml', '{http://schemas.openxmlformats.org/presentationml/2006/main}presentation',
             'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml'),
}


class InvalidDocument(ValueError):
    pass


class CheckLimit(ValueError):
    pass


def _xml(data):
    # Expat recognizes XML declarations in UTF-8/16/32. Reject declarations
    # before ElementTree can expand an internal entity, regardless of encoding.
    parser = expat.ParserCreate()

    def reject(*_args):
        raise InvalidDocument('XML DTD/entity declaration is not accepted')

    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    try:
        parser.Parse(data, True)
        return ET.fromstring(data)
    except (ET.ParseError, expat.ExpatError) as exc:
        raise InvalidDocument('Malformed required XML') from exc


def _zip(path, kind):
    required, root_name, content_type = OFFICE[kind]
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_MEMBERS:
                raise CheckLimit('Too many ZIP members')
            names = [i.filename for i in infos]
            if len(set(names)) != len(names):
                raise InvalidDocument('Duplicate ZIP member names')
            essentials = {'[Content_Types].xml', '_rels/.rels', required}
            if not essentials.issubset(names):
                raise InvalidDocument('Missing required Office package part')
            total = 0
            selected = {}
            for info in infos:
                name = info.filename
                if (name.startswith('/') or '\\' in name or
                        any(part in ('', '.', '..') for part in name.rstrip('/').split('/'))):
                    raise InvalidDocument('Unsafe ZIP member path')
                if info.flag_bits & 1:
                    raise InvalidDocument('Encrypted ZIP member')
                if info.file_size > MAX_ZIP_MEMBER:
                    raise CheckLimit('ZIP member exceeds inspection limit')
                total += info.file_size
                if total > MAX_ZIP_TOTAL:
                    raise CheckLimit('ZIP exceeds total inspection limit')
                if info.compress_size and info.file_size > 200 * info.compress_size:
                    raise CheckLimit('ZIP compression ratio exceeds inspection limit')
                chunks = [] if name in essentials else None
                if chunks is not None and info.file_size > MAX_XML:
                    raise CheckLimit('Required XML exceeds inspection limit')
                with archive.open(info) as stream:
                    read = 0
                    while block := stream.read(1024 * 1024):
                        read += len(block)
                        if read > info.file_size or read > MAX_ZIP_MEMBER:
                            raise CheckLimit('ZIP member expanded beyond declared size')
                        if chunks is not None:
                            chunks.append(block)
                    if read != info.file_size:
                        raise InvalidDocument('ZIP member size mismatch')
                # ZipExtFile checks CRC at EOF; every member is consumed.
                if chunks is not None:
                    selected[name] = b''.join(chunks)
            types = _xml(selected['[Content_Types].xml'])
            rels = _xml(selected['_rels/.rels'])
            body = _xml(selected[required])
            if types.tag != '{http://schemas.openxmlformats.org/package/2006/content-types}Types':
                raise InvalidDocument('Invalid content-types root')
            if rels.tag != '{http://schemas.openxmlformats.org/package/2006/relationships}Relationships':
                raise InvalidDocument('Invalid package relationships root')
            if body.tag != root_name:
                raise InvalidDocument('Unexpected Office main-part root')
            if not any(x.get('PartName') == '/' + required and
                       x.get('ContentType') == content_type for x in types):
                raise InvalidDocument('Main part not declared in content types')
            if not any(x.get('Target', '').lstrip('/') == required and
                       x.get('Type', '').endswith('/officeDocument') and
                       x.get('TargetMode', 'Internal') != 'External' for x in rels):
                raise InvalidDocument('No internal relationship to main part')
            return dict(validation='ZIP_CRC_AND_REQUIRED_XML_PASS', checked_members=len(infos),
                        checked_uncompressed_bytes=total)
    except (zipfile.BadZipFile, EOFError, RuntimeError, OSError, zlib.error,
            NotImplementedError) as exc:
        raise InvalidDocument('ZIP structure or CRC failed') from exc


def _ole(path):
    """Check CFB allocation and Word FIB without trusting an OLE signature alone."""
    size = path.stat().st_size
    with path.open('rb') as f:
        h = f.read(512)
        if len(h) < 512 or h[:8] != OLE_MAGIC:
            raise InvalidDocument('Not an OLE compound file')
        if h[28:30] != b'\xfe\xff':
            raise InvalidDocument('Invalid OLE byte order')
        shift, mini_shift = struct.unpack_from('<HH', h, 30)
        if shift not in (9, 12) or mini_shift != 6:
            raise InvalidDocument('Unsupported OLE sector geometry')
        sector = 1 << shift
        if size < sector or (size - sector) % sector:
            raise InvalidDocument('OLE file has a partial sector')
        sectors = size // sector - 1
        fat_count, directory_start = struct.unpack_from('<II', h, 44)
        if fat_count < 1 or fat_count > 109 or directory_start >= sectors:
            raise CheckLimit('OLE FAT layout exceeds bounded validator')
        difat = struct.unpack_from('<109I', h, 76)
        fat_ids = difat[:fat_count]
        if len(set(fat_ids)) != len(fat_ids) or any(x >= sectors for x in fat_ids):
            raise InvalidDocument('Invalid OLE FAT sector')

        def read_sector(index):
            if index >= sectors:
                raise InvalidDocument('OLE sector outside file')
            f.seek((index + 1) * sector)
            data = f.read(sector)
            if len(data) != sector:
                raise InvalidDocument('Short OLE sector')
            return data

        fat = b''.join(read_sector(x) for x in fat_ids)

        def next_sector(index):
            if index >= sectors or index * 4 + 4 > len(fat):
                raise InvalidDocument('OLE FAT index outside table')
            return struct.unpack_from('<I', fat, index * 4)[0]

        def chain(start, byte_limit):
            visited = set()
            index = start
            while index != 0xFFFFFFFE:
                if index in visited or len(visited) * sector >= byte_limit:
                    raise InvalidDocument('OLE chain loops or exceeds limit')
                visited.add(index)
                yield read_sector(index)
                index = next_sector(index)

        directory = b''.join(chain(directory_start, MAX_OLE_DIRECTORY))
        streams = {}
        for offset in range(0, len(directory), 128):
            entry = directory[offset:offset + 128]
            if len(entry) != 128:
                raise InvalidDocument('Partial OLE directory entry')
            name_len = struct.unpack_from('<H', entry, 64)[0]
            if entry[66] != 2 or not 2 <= name_len <= 64 or name_len % 2:
                continue
            try:
                name = entry[:name_len - 2].decode('utf-16le')
            except UnicodeError as exc:
                raise InvalidDocument('Invalid OLE stream name') from exc
            if name in streams:
                raise InvalidDocument('Duplicate OLE stream name')
            streams[name] = (struct.unpack_from('<I', entry, 116)[0],
                             struct.unpack_from('<Q', entry, 120)[0])
        if 'WordDocument' not in streams or not ({'0Table', '1Table'} & streams.keys()):
            raise InvalidDocument('Required Word streams absent')
        word_start, word_size = streams['WordDocument']
        if word_size < 32 or word_size > size:
            raise InvalidDocument('Invalid WordDocument stream size')
        # Small streams use the mini-FAT, which this bounded validator does not walk.
        if word_size < 4096:
            raise CheckLimit('Small Word stream needs mini-FAT inspection')
        word_blocks = chain(word_start, word_size + sector)
        first = next(word_blocks)
        if first[:2] != b'\xec\xa5':
            raise InvalidDocument('Word FIB marker absent')
        selected_table = '1Table' if struct.unpack_from('<H', first, 10)[0] & 0x0200 else '0Table'
        if selected_table not in streams:
            raise InvalidDocument('Selected Word table stream absent')
        read = sector
        for _ in word_blocks:
            read += sector
        if read < word_size:
            raise InvalidDocument('WordDocument stream chain is short')
        for table in (selected_table,):
            start, length = streams[table]
            if not 0 < length <= size:
                raise InvalidDocument('Invalid Word table stream size')
            if length < 4096:
                raise CheckLimit('Small Word table stream needs mini-FAT inspection')
            if sum(sector for _ in chain(start, length + sector)) < length:
                raise InvalidDocument('Word table stream chain is short')
        return dict(validation='OLE_DIRECTORY_AND_WORD_FIB_PASS',
                    checked_streams=['WordDocument', selected_table])


def _pdf(path, parse_pdf=True):
    size = path.stat().st_size
    with path.open('rb') as f:
        head = f.read(1024)
        if not head.startswith(b'%PDF-'):
            raise InvalidDocument('PDF header absent')
        f.seek(max(0, size - 1024 * 1024))
        tail = f.read(1024 * 1024)
    eof = tail.rfind(b'%%EOF')
    if eof < 0 or b'startxref' not in tail[:eof]:
        raise InvalidDocument('PDF final cross-reference marker absent')
    if size > MAX_PDF_PARSE:
        raise CheckLimit('PDF too large for bounded parser check')
    if not parse_pdf:
        return dict(validation='PDF_BOUNDARY_MARKERS_ONLY', parser='deferred_to_isolated_validation')
    try:
        from pypdf import PdfReader
    except ImportError:
        return dict(validation='PDF_BOUNDARY_MARKERS_ONLY', parser='unavailable')
    try:
        reader = PdfReader(str(path), strict=True)
        count = len(reader.pages)
        if count < 1 or count > 2000:
            raise InvalidDocument('PDF page count invalid or exceeds limit')
        # Resolve each page dictionary, without decoding potentially huge streams.
        for page in reader.pages:
            _ = page.get('/Type')
        return dict(validation='PDF_PAGE_TREE_PARSE_PASS', pages=count, parser='pypdf')
    except InvalidDocument:
        raise
    except Exception as exc:
        raise InvalidDocument('PDF parser rejected the file') from exc


def validate_document(path, kind=None, *, parse_pdf=True):
    """Return an honest classification for a regular saved file.

    `kind` can be doc, docx, xlsx, pptx or pdf; otherwise the extension is used.
    A pass never proves original-file completeness or semantic readability.
    """
    candidate = Path(path)
    result = dict(path=str(candidate), kind=(kind or candidate.suffix.lstrip('.')).lower(),
                  validation='NOT_VALIDATED', original_file_complete_proven=False)
    if result['kind'] not in {'doc', 'docx', 'xlsx', 'pptx', 'pdf'}:
        result['validation'] = 'UNSUPPORTED_KIND'
        return result
    try:
        if candidate.is_symlink() or (hasattr(candidate, 'is_junction') and candidate.is_junction()) or not candidate.is_file():
            raise InvalidDocument('Path is not a regular saved file')
        p = candidate.resolve(strict=True)
        before = p.stat()
        result['path'], result['bytes'] = str(p), before.st_size
        if not 0 < before.st_size <= MAX_FILE:
            raise CheckLimit('File size outside inspection limit')
        check = _ole if result['kind'] == 'doc' else _pdf if result['kind'] == 'pdf' else None
        result.update(_pdf(p, parse_pdf=parse_pdf) if result['kind']=='pdf' else check(p) if check else _zip(p, result['kind']))
        after = p.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise InvalidDocument('File changed during validation')
    except CheckLimit as exc:
        result.update(validation='NOT_VALIDATED_LIMIT', reason=str(exc))
    except (InvalidDocument, OSError) as exc:
        result.update(validation='STRUCTURE_FAILED', reason=str(exc))
    return result
