"""Read-only audit of completed QuietRescue document extractions.

Reads only the named recovery directory's immediate child manifests and their
referenced span validation files. Reports are written to the D: audit folder.
Each saved document is inspected in a separate process with a hard timeout.
"""

from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(r'R:\QuietRescue-Recovered-20261023')
OUT = Path(r'D:\codex-202609\2026-10-15\j-anytxt-searcher\outputs\quietrescue-audit-20261023')
KINDS = {'.doc', '.docx', '.xlsx', '.pptx', '.pdf'}
COMPLETE = 'CARVING_AND_VALIDATION_COMPLETE_ORIGINALS_RETAINED'
MAX_JSON = 32 * 1024**2
CHILD_CODE = ('import json,sys;sys.path.insert(0,sys.argv[1]);'
              'from document_validation import validate_document;'
              'print(json.dumps(validate_document(sys.argv[2]),ensure_ascii=False))')


def confined(path, parent):
    resolved = Path(path).resolve(strict=False)
    if not resolved.is_relative_to(parent.resolve(strict=True)):
        raise ValueError('Manifest path outside authorized R subtree')
    if resolved.is_symlink() or (hasattr(resolved, 'is_junction') and resolved.is_junction()):
        raise ValueError('Reparse path rejected')
    return resolved


def read_json(path, parent):
    p = confined(path, parent)
    if not p.is_file() or p.stat().st_size > MAX_JSON:
        raise ValueError('Manifest missing or exceeds inspection limit')
    with p.open('r', encoding='utf-8') as f:
        return json.load(f)


def inspect(path):
    env = {k: v for k, v in os.environ.items() if k.upper() in
           {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'SYSTEMDRIVE'}}
    try:
        completed = subprocess.run([sys.executable, '-I', '-c', CHILD_CODE,
                                    str(Path(__file__).parent), str(path)],
                                   capture_output=True, timeout=30, env=env,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        return dict(path=str(path), kind=path.suffix.lstrip('.').lower(),
                    validation='NOT_VALIDATED_TIMEOUT', original_file_complete_proven=False)
    if completed.returncode or len(completed.stdout) > 1024 * 1024:
        return dict(path=str(path), kind=path.suffix.lstrip('.').lower(),
                    validation='NOT_VALIDATED_PROCESS_ERROR', original_file_complete_proven=False)
    try:
        return json.loads(completed.stdout)
    except (ValueError, UnicodeError):
        return dict(path=str(path), kind=path.suffix.lstrip('.').lower(),
                    validation='NOT_VALIDATED_PROCESS_ERROR', original_file_complete_proven=False)


def save_progress(output):
    all_docs = [x for folder in output['folders'] for x in folder['documents']]
    output['summary'] = dict(completed_folders=sum(x.get('complete', False) for x in output['folders']),
                             checked_spans=sum(x['spans_checked'] for x in output['folders']),
                             documents=len(all_docs),
                             validation_counts=dict(Counter(x['validation'] for x in all_docs)),
                             skipped_folders=len(output['skipped']))
    OUT.mkdir(parents=True, exist_ok=True)
    temp = OUT / 'document-recovery-review.json.tmp'
    temp.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(OUT / 'document-recovery-review.json')


def audit():
    root = ROOT.resolve(strict=True)
    output = dict(scope=str(root), source_disk_reads=0, source_disk_writes=0,
                  saved_files_modified=0, original_file_complete_proven=False,
                  folders=[], summary={}, skipped=[], in_progress=True, pid=os.getpid())
    save_progress(output)
    for folder in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir() or folder.is_symlink() or folder.is_junction():
            continue
        manifest = folder / 'folder-extraction.json'
        if not manifest.is_file():
            continue
        try:
            folder = confined(folder, root)
            data = read_json(manifest, folder)
            if data.get('status') != COMPLETE:
                output['skipped'].append(dict(folder=str(folder), reason='not completed'))
                continue
            report = dict(folder=str(folder), documents=[], counts={}, spans_checked=0, complete=False)
            output['folders'].append(report)
            for run in data.get('runs', []):
                span = confined(run['directory'], folder)
                if span.parent != folder or not span.name.startswith('span-'):
                    raise ValueError('Unexpected span directory')
                validation = read_json(span / 'validation.json', span)
                report['spans_checked'] += 1
                for row in validation.get('files', []):
                    path = Path(row['path'])
                    if path.suffix.lower() not in KINDS:
                        continue
                    path = confined(path, span)
                    # Only paths explicitly listed in a completed span manifest.
                    result = inspect(path)
                    report['documents'].append(result)
                    report['counts'] = dict(Counter(x['validation'] for x in report['documents']))
                    save_progress(output)
            report['counts'] = dict(Counter(x['validation'] for x in report['documents']))
            report['complete'] = True
            save_progress(output)
            print(f"{folder.name}: {len(report['documents'])} documents", flush=True)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            output['skipped'].append(dict(folder=str(folder), reason=str(exc)))
            save_progress(output)
    output['in_progress'] = False
    save_progress(output)
    all_docs = [x for folder in output['folders'] for x in folder['documents']]
    lines = ['# Saved document recovery review', '',
             'Scope: completed folder-extraction manifests under `R:\\QuietRescue-Recovered-20261023`.',
             'Only saved R: files were read. A validation pass does not prove original-file completeness.', '',
             f"Completed folders: {output['summary']['completed_folders']}; checked spans: {output['summary']['checked_spans']}; document files: {len(all_docs)}.", '']
    for status, count in sorted(output['summary']['validation_counts'].items()):
        lines.append(f'- {status}: {count}')
    lines.extend(['', '## Per folder', ''])
    for folder in output['folders']:
        lines.append(f"### {Path(folder['folder']).name}")
        lines.append(f"Spans: {folder['spans_checked']}; document files: {len(folder['documents'])}.")
        for item in folder['documents']:
            lines.append(f"- `{item['validation']}`: `{item['path']}`" +
                         (f" ({item['reason']})" if item.get('reason') else ''))
        lines.append('')
    if output['skipped']:
        lines.extend(['## Skipped manifests', ''])
        for item in output['skipped']:
            lines.append(f"- `{item['folder']}`: {item['reason']}")
    (OUT / 'document-recovery-review.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return output['summary']


def parse_pending_pdfs():
    """Recheck boundary-only PDFs with this interpreter's optional parser."""
    report_path = OUT / 'document-recovery-review.json'
    output = json.loads(report_path.read_text(encoding='utf-8'))
    if output.get('in_progress') or Path(output['scope']).resolve() != ROOT.resolve(strict=True):
        raise ValueError('First audit must finish for the authorized R scope')
    output['in_progress'] = True
    output['phase'] = 'pdf_parser'
    output['pid'] = os.getpid()
    save_progress(output)
    for folder in output['folders']:
        for index, item in enumerate(folder['documents']):
            if item['validation'] != 'PDF_BOUNDARY_MARKERS_ONLY':
                continue
            path = confined(item['path'], ROOT)
            folder['documents'][index] = inspect(path)
            folder['counts'] = dict(Counter(x['validation'] for x in folder['documents']))
            save_progress(output)
    output['in_progress'] = False
    output['phase'] = 'complete'
    save_progress(output)
    # Refresh the readable report after upgrading PDF classifications.
    lines = ['# Saved document recovery review', '',
             'Only files referenced by completed manifests under `R:\\QuietRescue-Recovered-20261023` were read.',
             'A validation pass does not prove original-file completeness.', '',
             f"Folders: {output['summary']['completed_folders']}; spans: {output['summary']['checked_spans']}; documents: {output['summary']['documents']}.", '']
    for status, count in sorted(output['summary']['validation_counts'].items()):
        lines.append(f'- {status}: {count}')
    lines.extend(['', '## Per folder', ''])
    for folder in output['folders']:
        lines.extend([f"### {Path(folder['folder']).name}",
                      f"Spans: {folder['spans_checked']}; documents: {len(folder['documents'])}."])
        for item in folder['documents']:
            lines.append(f"- `{item['validation']}`: `{item['path']}`" +
                         (f" ({item['reason']})" if item.get('reason') else ''))
        lines.append('')
    if output['skipped']:
        lines.extend(['## Skipped manifests', ''])
        for item in output['skipped']:
            lines.append(f"- `{item['folder']}`: {item['reason']}")
    (OUT / 'document-recovery-review.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return output['summary']


if __name__ == '__main__':
    print(json.dumps(parse_pending_pdfs() if '--parse-pdfs' in sys.argv else audit(),
                     ensure_ascii=False))
