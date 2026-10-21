# QuietRescue 1.2.0 — Windows x64 source preview

This is a review build of the local recovery utility. It is not a claim that the complete specification or physical-disk recovery has passed acceptance. The source builds a portable Windows EXE with the bundled Python/Tk/Pillow runtime; this version has not yet had its rebuilt EXE launch/UI acceptance run.

## Safety changes

- Creating a physical-disk job only writes a draft. A separate review step displays source/destination identities, byte scope, imported exclusions, no-retry policy and reserve before it records approval. The approval is bound to the exact plan SHA-256. Any plan edit, identity change or newly added exclusion blocks reads.
- A task configured with an existing map imports policy guards and previous attempts separately, and can coordinate through a map-specific controller lock plus a source-identity mutex. Missing, incomplete or changed maps fail closed; historical requests are never retried.
- Per-stage and whole-plan cumulative byte limits are tracked independently across passes. Recovery of an interrupted request requires a matching durable receipt and saved-copy hash; otherwise it remains unconfirmed.
- Startup, permission, disconnect, CRC, timeout, and destination write/flush failures have distinct classifications. A timeout or disconnect is not labelled a physical bad sector and is never retried automatically.
- Avoidance reports preserve the distinction between observed read errors, unconfirmed requests, policy guards, and prior attempts. None is a precise physical bad-sector diagnosis.
- **The physical reader has not passed disposable-device and I/O cancellation acceptance, so physical read/approval remains locked in 1.2.** Use only source review, synthetic image tests, and plan inspection; do not use this version to read a failing source drive.
- Saved-copy verification and media recovery use the destination project only; they do not require the source disk to be present. Output and export locations are checked so they are not the source physical disk.
- Stop status distinguishes a request from a completed stop. Verification reports it cannot currently be interrupted. The maintenance tab is read-only preview only: there is no CHKDSK `/f`, physical bad-sector write, formatting or partition-table write action.

## Current workflow and limits

1. Run `Start-QuietRescue.cmd`, refresh the physical disk list, and select a healthy destination on a different physical disk.
2. Set a byte range, per-stage GB limit, and whole-plan cumulative cap. Bounded chaining is implemented, but physical capture remains locked until the reader passes hardware acceptance.
3. Keep the whole task folder. It contains the plan, approval, mapping journal, segments and verification report.
4. Recoverable built-in carving is limited to decodable JPEG/PNG bytes in verified contiguous ranges. Original paths/names and fragmented files are not reconstructed by that feature. PhotoRec 7.2 is an optional external tool and must be installed manually; its output is not proof of a complete file.
5. Partition output is a proposal. Candidate segments are explicitly marked `NOT_PROVEN_HEALTHY`; a map guard is not a measured physical bad-sector boundary.

The current 19 source tests use synthetic file images only. They cover cumulative/stage caps, receipt/hash reconciliation, failure classification, live-exclusion changes, no-retry behavior, reserve checks, and read-only partition preview. They do not cover actual disk hardware, hung USB I/O cancellation, power loss, full NTFS/MFT reconstruction, whole-video/DVD/RAW recovery, or destructive maintenance. See [implementation status](docs/IMPLEMENTATION-STATUS.zh-TW.md).

The older 1.1.0 EXE has a separate historical acceptance report; it is not evidence that the current 1.2.0 source or EXE passed. Version 1.2.0 has not been rebuilt, and physical capture remains locked. This tool cannot repair a physically failing disk or promise recovery of overwritten or unreadable bytes.

- [使用說明](docs/USAGE.zh-TW.md)
- [實作與驗收狀態](docs/IMPLEMENTATION-STATUS.zh-TW.md)
- [Build](docs/BUILD.md)
- [MIT license](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)

UI language: Traditional Chinese. Windows x64.
