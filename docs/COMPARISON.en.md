# Feature comparison

| Tool | Primary role | Recovery / repair | Where QuietRescue fits |
|---|---|---|---|
| QuietRescue | Small Windows GUI for bounded imaging | Durable request map, hash checks, JPEG/PNG extraction, optional PhotoRec; guarded CHKDSK launch | Inspectable Python code and explicit no-retry policy; prototype with limited hardware coverage |
| DiskGenius | Broad disk/partition and recovery suite | File/partition recovery, cloning and bad-sector tools; capabilities vary by edition | QuietRescue offers narrower auditable behavior, not proven better recovery or speed |
| TestDisk / PhotoRec | Filesystem/partition recovery and signature carving | TestDisk works with partition/filesystem structures; PhotoRec carves many formats, generally losing names/tree | QuietRescue uses PhotoRec externally; it does not replace TestDisk metadata recovery |
| GNU ddrescue | Advanced rescue imaging with mapfiles | Resume, multiple passes and configurable retries | QuietRescue gives a Windows photo-oriented UI; its JSONL map is not ddrescue-compatible |
| Hex/binary editor | Manual byte inspection/editing | Specialist inspection and targeted changes, depending on product | QuietRescue automates bounded capture and verification; it is not a forensic editor |

Choose QuietRescue for understandable local workflows and conservative stop behavior. Choose specialized tools when you need filesystem reconstruction, mature large-drive recovery strategies or forensic interpretation. A no-retry policy may sacrifice recoverable data; it is a tradeoff, not a universally superior method. No software here can promise physical media rejuvenation. Avoidance CSV is advice, not bad-block repair.

## Sources / 來源 / 出典

Reviewed 2026-10-21. Features and licensing may change; this is not a recovery-rate or speed benchmark.

- [DiskGenius cloning](https://www.diskgenius.com/manual/clone-disk.php)
- [DiskGenius bad-sector checks and repair limitations](https://www.diskgenius.com/manual/verify-or-repair-bad-sectors.php)
- [TestDisk / PhotoRec overview](https://www.cgsecurity.org/testdisk_doc/index.html)
- [PhotoRec filename and filesystem limitations](https://www.cgsecurity.org/testdisk_doc/photorec.html)
- [GNU ddrescue manual](https://www.gnu.org/software/ddrescue/manual/ddrescue_manual.html)

Hex/binary editor is a category, not a specific tested product; capabilities vary by implementation.

## What the executable release adds

- Download, extract and run one EXE; no Python setup. Portability is convenient, not unique to this product or evidence of better recovery than DiskGenius.
- The same bundled executable runs a controlled reader worker, so checkpoint continuation no longer depends on an installed interpreter.
- A synthetic local demo shows photo and native video preview without opening a physical source disk.
- Inspectable request maps, explicit stop rules and hash verification make the workflow understandable. They do not establish better recovery rates, speed or lower hardware risk than DiskGenius or ddrescue.
- DiskGenius has broader partition/filesystem functions; TestDisk handles structures QuietRescue does not reconstruct; PhotoRec supports many formats; ddrescue offers mature multi-pass strategies. This release does not replace those capabilities.

Actual EXE acceptance covers UAC administrator token, a two-pass synthetic image with unique requests, byte-identical photo recovery and advancing AVI playback. It does not validate all video codecs, failing hardware, physical repair or Windows versions beyond the tested host.
