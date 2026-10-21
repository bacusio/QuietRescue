# Contributing

Keep source I/O read-only. Preserve REQUESTED before I/O and skip uncertain outcomes. Never test on an irreplaceable disk. Use artificial image files for regression tests. Run `python tests.py` on Windows after engine changes. UI changes must keep physical identity and different-destination checks.

Submit minimal patches with behavior, validation and limitations. Do not attach real recovery data, logs containing serials, secrets or personal file names. There is no CI workflow with elevated privileges in this source archive.
