# QuietRescue 1.2.2 — saved-image recovery and region warnings

The progress band displays saved, reported-saved, unconfirmed, error, skipped and unknown ranges, plus an avoidance-draft overlay. It refreshes the selected progress JSON every five seconds and checks source serial/capacity before applying it. Red indicates an observed read failure; it does not establish a physical bad-sector boundary. Saved and merely attempted ranges remain distinct.

This release adds saved-image TestDisk analysis, PhotoRec checkpoint resume, verified cross-job MKV reconstruction and MFT-name export. Chinese input paths can use a verified temporary image. Physical reads still require a reviewed plan; no partition writeback, formatting or write-based repair is provided.

## Download package

The core Windows ZIP contains the exact requested image-paths executable, licenses and instructions. PhotoRec/TestDisk binaries are not redistributed. Run `powershell -File .\Install-OfficialTools.ps1` once to download the pinned official 7.2 archive directly from CGSecurity, or pass `-ArchivePath` for an offline official ZIP. The installer verifies archive/executable hashes, refuses to overwrite an existing install and does not start scanning. Retained staging files may be removed after successful installation.

Official download: https://www.cgsecurity.org/wiki/TestDisk_Download

EXE SHA-256: `01388f699ba99acf0796575d8b830d6b38da4e95d99ee556c44dc1ff7e0eb9b5`.

## Validation

- 98 source regression tests passed, including progress identity/ranges, saved-map recovery and checkpoint guards.
- An actual interrupted PhotoRec synthetic scan resumed from its real session and restored a byte-identical JPEG.
- The preceding resume255 binary passed elevated synthetic photo/video/checkpoint acceptance. The exact image-paths binary has package-content verification, but its separate elevated runtime acceptance is pending. This is a prerelease, not a claim of physical-fault or all-buttons acceptance.
- No recovered personal files, disk identities, maps or private logs are included in this repository/package.

Large recovered movies require complete saved coverage across chunks. A standalone 1GB chunk is not necessarily a standalone movie. Full available-stream decoding does not prove original filename or original file completeness.


## Subsequent exact-binary acceptance

The published image-paths EXE (unchanged SHA-256) has now passed elevated synthetic runtime acceptance: admin/frozen true, two unique checkpoint requests, 2,097,152 verified bytes, byte-identical photo with preview, and video playback advanced from 0 to 1267 ms. No physical-source reads or writes. This supersedes the pending exact-binary acceptance note above and inside the already-published ZIP; it does not validate physical-fault behavior or every GUI control. See validation-image-paths-exe.json.
