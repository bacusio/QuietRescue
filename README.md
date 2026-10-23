> Latest: QuietRescue 1.2.2 prerelease. See [release notes and package setup](docs/RELEASE-1.2.2.md). The notes below may describe earlier versions.

# QuietRescue 1.2.1 — Windows x64

Version 1.2.1 restores the read-only physical-disk reader present in 1.1 while keeping 1.2 plan review, skip maps, checkpoint verification and the progress band. A physical read still requires the user to review and approve an exact plan. Opening the app alone does not scan disks. Source tests use synthetic data; the reader and I/O cancellation have not been validated on a failing physical drive.

The imaging page can load a `disk-rescue-progress/v1` JSON file. It refreshes saved, reported, unconfirmed, error, skipped, unknown and draft ranges every five seconds. The blue cursor updates the start-byte field. Ranges apply only when source serial and capacity match exactly. The band reads the progress JSON only and does not start disk I/O.

## Reading and safeguards

- A physical job starts as a draft. Review the source and destination identities, byte range, per-stage and cumulative limits, imported exclusions and no-retry policy, then explicitly approve that plan. Approval is bound to the complete plan SHA-256. Changes to the plan, device identity or skip map require a new review.
- The source is opened read-only. Each request is 1 MiB. The first error, an 8-second timeout or a read taking over 2 seconds stops the pass; the application does not retry. Operating-system or device-firmware retries are outside application control.
- Disconnects, CRC errors, timeouts or unconfirmed outcomes, access failures, and destination write failures are recorded separately. They do not establish exact physical bad-sector boundaries.
- Source-identity mutexes, exclusion of prior requests, destination-space reserve, journal and segment SHA-256 verification remain enabled. A stop request completes only after the current I/O and checkpoint are safely settled.
- The application does not write-repair bad sectors, format disks or write partition tables. Avoidance partition output is a proposal; candidate ranges are not certified healthy.

## Use and limits

1. Extract the Windows x64 ZIP and launch `QuietRescue.exe`; Python is not required. Use the Windows UAC prompt normally. Identify the source by model, serial and capacity, and choose a destination on another healthy physical disk.
2. Create a draft, inspect source and destination, byte range, imported skip map, stage limits and reserve, then select **Review and approve plan**. Reads begin only after approval and an explicit **Start/Resume** action.
3. Keep the entire job folder, including plan, approval, `map.jsonl`, segments and verification report. Every REQUESTED range, including unknown outcomes, is excluded from retry. Do not delete records to force a reread.
4. Verify saved copies before extracting decodable JPEG/PNG from continuous verified bytes. Built-in carving cannot restore original names or fragmented files. PhotoRec is optional.
5. Check full duration, seek points and audio for recovered videos. A file signature or normal tool exit does not prove completeness.

The 20 source tests use synthetic files and progress JSON. No physical source was read in this release build, and failing-drive USB cancellation, power-loss behavior and complete-media recovery have not been validated. QuietRescue cannot repair physical damage or guarantee recovery of overwritten or unreadable data.

- [Usage](docs/USAGE.en.md)
- [Implementation status (Traditional Chinese)](docs/IMPLEMENTATION-STATUS.zh-TW.md)
- [Build](docs/BUILD.md)
- [MIT license](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)

UI language: Traditional Chinese. Windows x64.
