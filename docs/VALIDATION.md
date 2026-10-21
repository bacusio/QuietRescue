# Validation and limits

Run `python tests.py` in the configured environment on Windows. Tests use synthetic local image files, never physical disks. Coverage includes byte-for-byte export, timeout/no retry, unresolved request exclusion, altered-hash rejection, JPEG extraction, space-floor behavior and a real reader subprocess.

The pre-publication local build also exercised PhotoRec 7.2 on an artificial JPEG image with byte-for-byte equality. That is not a benchmark on damaged media. Private images, photos, serials, logs and drive-specific startup automation are deliberately not distributed.

Public-package test results are saved in validation-result.txt after packaging. No physical-disk or CHKDSK write test is part of the package checks. No recovery-rate, lifespan, broad USB compatibility, power-loss durability or full-video claim is made.

Known limits: map/hash verification loads metadata into memory and overlap checking is quadratic; multi-terabyte jobs may need optimization. Timeout kills a worker but cannot guarantee USB/kernel I/O has finished. Do not continue if worker exit is unconfirmed. PhotoRec space protection is polling-based. Public UI is Chinese; documentation is English, Traditional Chinese and Japanese. Legacy private maps and existing controllers are not imported or coordinated automatically.
