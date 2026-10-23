# GitHub release checklist

The local deliverables are a source ZIP and a Windows-x64 release ZIP. No repository or Release has been uploaded by this task. Review MIT LICENSE, THIRD_PARTY_NOTICES, README translations and docs/EXE-VALIDATION.md. The executable is unsigned.

Keep recovery images, personal logs, serial numbers and vendor binaries out of Git. The generated synthetic demo files are safe to publish. Initialize a fresh repository in the extracted source folder:

```powershell
git init -b main
git add .
git diff --cached --stat
git commit -m "Release QuietRescue 1.1 standalone preview"
```

Use your own repository URL as origin. Review and push main, then create a release/tag such as v1.1.0. Upload QuietRescue-1.1.0-Windows-x64.zip and its SHA-256 file as release assets. The ZIP contains one EXE plus usage and license notices, with no Python installation step. Keep the notices with redistributions. A separate source ZIP is supplied. Do not describe this as a signed installer or as physical bad-sector repair.
