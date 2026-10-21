# Publishing QuietRescue

Before publishing, review the MIT license, third-party notices, translated READMEs, and `docs/EXE-VALIDATION.md`. The executable is unsigned.

Keep recovery images, personal logs, drive serial numbers, and vendor binaries out of the repository. Only the generated synthetic demo media is included. The supplied Windows x64 ZIP contains the standalone EXE, usage documents, and license notices; users do not need Python. The source ZIP is a separate release asset.

Create a release for tag `v1.1.0` and attach:

- `QuietRescue-1.1.0-Windows-x64.zip`
- `QuietRescue-1.1.0-source.zip`
- `SHA256SUMS.txt`

Do not describe this build as code-signed, an installer, or a physical bad-sector repair tool.
