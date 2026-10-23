# QuietRescue 1.2.1

- Restored the read-only physical-disk reader from 1.1 and removed the global hard-lock flag. Reads are available after explicit review and approval of the exact plan; the default startup remains idle.
- Retained plan-hash approval, device identity checks, map freshness checks, exclusion of prior and unconfirmed requests, no application retries, space reserve and durable checkpoint verification.
- Retained the whole-disk progress band synchronized with the byte cursor and exact serial/capacity matching.
- Kept regression coverage proving approval is bound to the exact plan and capture cannot start without an approval record.
- Physical hardware and failing-drive I/O cancellation were not tested in this release build; synthetic source tests only.

## 1.2.0 historical notes

- Added independently bounded chained stages and cumulative plan budget, with final-state persistence.
- Reconciled interrupted requests only from a durable receipt and matching saved-copy hash; unresolved data remains excluded without rereading the source.
- Classified startup, access, disconnect, CRC, timeout/cancel, and destination failures independently.
- Preserved prior-attempt and guard provenance in avoidance exports and partition previews.
- Version 1.2.0 temporarily disabled physical capture pending disposable-device and I/O cancellation acceptance. Version 1.2.1 removes that application-level hard lock and restores the reviewed read-only path.

## 1.1.0 historical notes

- Added plan draft/review/approval flow for physical disk tasks, with approval bound to a SHA-256 of the complete read plan and revalidation before parent and worker opens a physical source.
- Added optional existing-map exclusions, source-identity physical-disk mutex and optional controller interoperation lock.
- Separated saved-copy verification from source availability, and checked output destinations against source identity.
- Replaced CHKDSK /f action with read-only maintenance/partition-layout preview.

Not implemented: automatic physical bad-sector repair, formatting, partition-table writes, or complete filesystem/MFT extraction.
