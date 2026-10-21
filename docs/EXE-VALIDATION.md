# Windows EXE acceptance — 2026-10-21

| Check | Observed result |
|---|---|
| Release EXE | Windows AMD64, 19,246,689 bytes |
| Manifest and UAC | requireAdministrator manifest; normal ShellExecute runas succeeded; IsUserAnAdmin=true inside EXE |
| Bundled runtime | frozen=true; executable copied alone into a separate directory; PATH contained only Windows directories |
| Checkpoint resume | First 1 MiB pass incomplete, second pass complete; 2 unique REQUESTED ranges, no repeats |
| Saved image | 2,097,152 bytes verified; exported bytes equal artificial source |
| Recovered JPEG | Bytes equal the original synthetic JPEG; Tk image preview created and visible photo UI inspected |
| Embedded video | Native Windows AVI position advanced 0 to 1267 ms after playback started |
| Source regression checks | 8 tests passed, including uncertain request, mixed JSON guards, timeout and space reserve |
| Physical source access | 0 reads and 0 writes in EXE acceptance |

SHA-256 of the tested final EXE: `f552a211e214702db9fc8e880f86b2e80c32a0c0ef3beac66b549930adbc7d0f`.

The final executable remained open after acceptance. This was a Windows 11 x64 host with Python installed for development; it was not a clean VM test on a machine with Python uninstalled. The isolated EXE directory and restricted PATH test demonstrated that no external Python executable or adjacent source files were required. No raw-disk, CHKDSK, partition-writing or complete-film recovery test was performed for this release.

AVI video playback was verified by the native player's advancing position; codec support for MKV, MP4 and other inputs is not guaranteed. Use the system-player fallback for unsupported codecs. The executable is unsigned. UAC acceptance does not constitute a signing/reputation endorsement. No automated bypass of UAC or Windows security was used.

The machine-readable sanitized result is in validation-result.json. No personal photos, serial numbers, raw drive data or private logs are included.
