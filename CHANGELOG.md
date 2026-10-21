# QuietRescue 1.2.0 source preview

- Added independently bounded chained stages and cumulative plan budget, with final-state persistence.
- Reconcile interrupted requests only from a durable receipt and matching saved-copy hash; unresolved data remains excluded without rereading the source.
- Classify startup, access, disconnect, CRC, timeout/cancel, and destination failures independently.
- Preserve prior-attempt and guard provenance in avoidance exports and partition previews.
- Keep physical capture/approval disabled until disposable-device and I/O cancellation acceptance is completed.
- Expanded synthetic coverage to 19 tests; no physical source was read.

- Added plan draft/review/approval flow for physical disk tasks, with approval bound to a SHA-256 of the complete read plan and revalidation before parent and worker opens a physical source.
- Added optional existing-map exclusions and reject stale plans when new protected ranges appear.
- Added source-identity physical-disk mutex and optional controller interoperation lock.
- Separated saved-copy verification from source availability, and checked output destinations against source identity.
- Replaced CHKDSK /f action with read-only maintenance/partition-layout preview.
- Added candidate partition segments with explicit unknown-health labels and current partition context only when source identity can be matched.
- Added tests for approval invalidation, live map growth, source identity mutex, and maintenance preview classification.

Not yet implemented: chained unattended passes, transactional power-loss recovery, complete filesystem/MFT extraction, source-aware whole-file integrity mapping, all A01-A12 acceptance, automatic physical bad-sector repair, formatting or partition-table writes.
