# 1.2.2 local development status

This is an unfinished local source build, not a release or a replacement for the
existing tested imaging controller. No physical-source reader was changed.

Implemented and tested:
- Bundled PhotoRec 7.2 discovery with executable SHA-256 validation.
- Saved `.bin`, `.img`, `.dd`, `.raw`, and `.partial` input selection.
- Private contiguous staging copy: original image remains unchanged.
- ASCII/Windows short-path handling; fail before extraction when unsuitable.
- Copy progress and extraction elapsed time in the UI, plus durable JSON state.
- 6 GB output-space reserve, stop request, four-hour extraction bound.
- Check diagnostic output as well as exit code: PhotoRec can return zero on a
  command syntax failure.
- A real synthetic `.bin` PhotoRec smoke test recovered the original JPEG
  byte-for-byte and left the input unchanged. The first packaging test caught a
  missing `63/cygwin` terminfo file; the dependency is now included and the actual
  test passes. All 20 existing synthetic regression tests pass.
- Saved-image TestDisk old-partition analysis with fixed `analyse,search`
  commands and a Windows share-read-only lease held through execution. A real
  test found a FAT16 partition in a synthetic image without an MBR, verified a
  concurrent write-open was denied, and verified the image hash was unchanged.
  Log addresses are relative to the image, never silently physical addresses.
- Cross-job MKV header discovery and reconstruction from GOOD mappings only,
  source serial/size agreement, conflicting-overlap rejection, bounded-memory
  hashing, no zero-filled gaps, and optional full FFmpeg audio/video decode.
  Nineteen focused tests pass. A real synthetic movie split inside its EBML header
  across two job folders was restored byte-for-byte and fully decoded.
- Completed cross-job movies are rehashed and reused on another run of the same
  selected jobs/destination, with an exclusive process lock. Changed outputs or
  mappings and moved outputs stop for review rather than silently overwriting or
  recreating files. Interrupted exports now checkpoint fsynced bytes and their
  SHA256. Resume verifies source binding, source blocks and the saved prefix
  before continuing; unknown or changed partial files are never adopted.
  Tests cover interruption through mapped_videos.recover and the receipt-written,
  rename-not-finished boundary. Only an authenticated extra partial tail is trimmed.
- Real Tk callback/background-worker integration passed on synthetic jobs;
  physical-disk identity was mocked for this UI test. This is not manual visual
  acceptance and does not claim a fault-disk test.
- A local Windows executable was built successfully in dist, with external
  vendor runtime dependencies copied alongside it. The packaged EXE has not
  completed its own runtime acceptance test.

Not yet integrated or accepted:
- Packaged executable runtime/visual acceptance and interrupted PhotoRec scan resume.
- Compatibility import for every older manifest variant.
- Extension/attribute-list reconciliation.
- Verified-original-image deletion through the UI.

2026-10-23 follow-up acceptance:
- 47 source tests passed: 19 saved-range/resume, 8 document-structure, 20 engine.
- Actual PhotoRec synthetic JPEG extraction remained byte-identical, with input
  unchanged. Restricted Windows namespace access initially blocked Cygwin; the
  same saved-image-only test passed outside that restriction.
- Actual FFmpeg split-MKV reconstruction and Tk callback/worker test passed.
- DOC/OLE, OOXML CRC/required XML, and PDF checks report their exact validation
  level. DTD/entity XML is refused, including UTF-16. The GUI defers PDF parser
  work to isolated validation and reports boundary markers only; it never treats
  that result as a complete restored document.
- Windows executable rebuilt with checkpoint resume and document checks.
  This build is not claimed to have passed frozen-EXE visual/runtime acceptance.

2026-10-24 MFT integration:
- The gallery exposes saved-record original-name restoration. It requires explicit
  physical volume start, cluster size and geometry evidence; no automatic geometry
  inference. The record and destination are rejected if on the source physical disk.
- Nonresident, uncompressed, fully initialized, completely saved streams can be
  reconstructed across fragmented extents. Missing bytes, sparse/compressed streams,
  attribute lists, unsafe filenames and existing outputs are refused. Metadata and
  output receipts retain the geometry basis and do not assert original completeness.
- Five parser tests and three reconstruction tests passed. Three GUI-handler tests
  passed using mocked dialogs, geometry/record parsing and disk identity, while
  actually exporting synthetic saved fragments. These are not visual acceptance.
- No newly recovered real file is claimed from this feature yet. Earlier
  app/media/source tests also passed.
- Final targeted regression run: 58 distinct tests passed with Python 3.13.

Resident MFT follow-up:
- Original-name resident output is now supported through the same entry point.
  Contents come from the USA-fixed saved record; no disk extent is opened.
  Output and sidecar collisions are refused, a 6GB reserve is enforced, and
  stop-before-write leaves no output. An interrupted tiny export is retained
  for review, not silently overwritten. Record origin remains unproven unless
  independently linked to the source disk; the receipt explicitly states this.
- Five resident tests plus eleven named/parser/UI tests passed, covering Unicode,
  fixups inside file contents, empty files, existing-output protection, stop and
  space reserve. No additional real recovered file is claimed.

Completed cleanup-ledger compatibility:
- SavedRanges can import completed lossless-cleanup-ledger*.json explicitly from
  the selected recovery root. The mapped-video and MFT UI flows discover these
  ledgers in the selected output folder. Missing originals without a receipt stay
  unavailable; the original physical-source identity still comes from job plans.
- Replacement MKV files must remain inside that selected root, with valid bounds.
  Before use, both the full replacement container hash and each original GOOD
  block hash are checked. No original bin is recreated and no file is deleted.
- Five regression tests cover exact reconstruction, container tampering outside
  the selected block, absent receipts, incomplete cleanup and out-of-root paths.

GPT mode follow-up:
- Saved-image TestDisk UI now accepts only GPT or MBR, using fixed upstream
  partition_gpt/partition_i386 plus analyse,search commands. No write command.
- Actual TestDisk GPT-mode search on the existing synthetic lost-partition image
  found its FAT16 signature and retained the input hash. This is a mode/search
  acceptance test, not exhaustive GPT table recovery compatibility.
- Packaged EXE acceptance request returned Windows user-cancelled at UAC; the EXE
  acceptance did not run. Do not claim packaged UI/runtime acceptance from source
  unit tests or the external TestDisk test.

PhotoRec extraction completion is not proof of original-file completeness or of
pre-format age. Never delete an original image merely because a PhotoRec run
completed. Current recovery work retains the original unless every byte is
reproducible from a separately verified saved output with a recorded offset/hash.

Observed reason for different movie outcomes: previous complete movie captures
included the entire declared EBML segment, while individual 1 GB chunks can begin
or end inside a movie. Cross-folder reconstruction works only where saved,
verified physical ranges cover the whole file without a gap; some apparently
covered files still fail real decoding and remain classified as failed.

PhotoRec saved-session follow-up:
- UI provides a saved-job resume entry. Preflight requires STOPPED_ERROR,
  verified staged-image size/SHA-256 and an in-bounds saved session. Missing
  checkpoints never silently restart extraction. Original sessions are retained.
- Resume explicitly supplies the staged image before `/cmd resume`. Upstream
  phmain.c otherwise calls hd_parse when list_disk is empty. An initial bare
  resume experiment was stopped; absence of physical reads was not proven for
  that initial experiment. It is not counted as a successful safety test.
- The runner holds a Windows read-only image lease and a task lock, uses a new
  output directory, keeps a 6GB reserve and stops on cancellation or timeout.
  Later attempts require a confirmed child exit, matching image identity and a
  valid session in the latest attempt directory. Missing latest progress never
  falls back to an older session. Unknown exits remain blocked. Stage copies
  are retained; actual uncontrolled application-crash recovery is unverified.
- Actual runner test recovered a byte-identical JPEG from a synthetic session;
  staged image and original session were unchanged. This does not prove a real
  interrupted PhotoRec session resumes correctly or that movies are complete.
- 87 targeted regression tests passed after integration. Packaged interactive
  acceptance remains unverified; prior UAC cancellation is still unresolved.
- Initial extraction now also passes the image as the first positional argument
  and holds a Windows read-only lease while PhotoRec runs. Both initial and
  resumed extraction reject a zero exit code when photorec.ses remains; upstream
  phrecn.c removes that session only after the final successful search phase.

2026-10-24 frozen-EXE programmatic acceptance:
- A new normal UAC launch succeeded. acceptance.json reported admin=true and
  frozen=true, two unique saved-file requests, 2,097,152 verified bytes,
  byte-identical recovered JPEG and a successfully loaded Tk image preview.
- Native video playback advanced from 0 to 1200 ms. These are actual packaged
  runtime checks, not source-only tests, but do not constitute manual visual QA.
- Evidence: outputs/quietrescue-audit-20261023/exe-acceptance-20261024-031850/
  acceptance.json. This supersedes the earlier UAC-cancelled acceptance blocker.
- This test covers the imaging engine's synthetic checkpoint path, not PhotoRec
  real interrupted-scan recovery, physical-fault behavior or all GUI controls.

Actual PhotoRec checkpoint interruption acceptance:
- A real PhotoRec process reading a 2GiB synthetic saved image was suspended
  after about 140MB of process I/O, resumed after its checkpoint interval,
  and terminated after observing its actual session file. The process exit was
  confirmed before starting a separate resume attempt.
- That real checkpoint exposed whole-image partition order 255; the parser now
  accepts 255 and legacy 0 only under partition_none. Synthetic order-0 tests
  alone had not covered this upstream output.
- Resume from the preserved real session restored a byte-identical JPEG. The
  complete synthetic image hash matched its independently reconstructed expected
  contents, and the original checkpoint was unchanged. Evidence:
  outputs/quietrescue-audit-20261023/real-interruption-1792782832705699000/test-status.json.
- This verifies one forced PhotoRec-process interruption with an intact real
  checkpoint. It does not verify power loss, torn filesystem writes, an orphaned
  worker after controller crash, or physical-disk failure recovery.

2026-10-24 combined regression after saved-image path staging:
- Ran unittest modules tests_resume_ui, tests_photorec_session,
  tests_photorec_completion, tests_partition_modes, tests_partition_staging,
  tests_cleanup_import, tests_resident_recovery, tests_named_ui,
  tests_named_recovery, tests_ntfs_names, tests_saved_ranges,
  tests_document_validation and tests: 98 tests passed in 14.148 seconds.
- This covers source-level synthetic tests, including low-space/cancellation
  staging guards. It does not upgrade the image-paths executable to runtime
  accepted, or establish physical-fault recovery behavior.
