# QuietRescue 1.2.0 safety and checkpoint hardening

## Proposed commit

`Harden QuietRescue 1.2 recovery safety`

## Pull request

### Summary

- Track per-stage and whole-plan byte budgets independently and persist the final state after every chained pass.
- Reconcile an interrupted request only when its durable receipt, saved extent length, and SHA-256 agree; otherwise preserve it as unconfirmed and never reread it.
- Distinguish reader startup, permission, disconnect, CRC, timeout/cancel, destination write, and destination flush failures.
- Keep prior attempts, policy guards, observed read errors, and unconfirmed ranges separately labelled in avoidance reports.
- Keep physical capture and approval disabled until the reader passes disposable-device and I/O cancellation acceptance.
- Remove machine-specific disk identifiers and local rescue paths from the published source.

### Validation

- `python -m py_compile app.py engine.py maintenance.py media.py tests.py`
- `python -m unittest -v` — 19 synthetic-image tests passed after publication sanitization.
- No physical source disk was read or written. The 1.2.0 EXE was not rebuilt or validated. Physical capture remains locked pending disposable-device and cancellation tests.

### Commit message body

Bound chained capture to per-stage and plan-wide byte limits. Reconcile interrupted requests only from destination receipts and hashes, classify failures independently, preserve avoidance provenance, and keep unvalidated physical capture disabled.
