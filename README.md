# QuietRescue 1.1 — portable Windows EXE

[English](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

Download the Windows-x64 ZIP, extract it to a local folder, and double-click **QuietRescue.exe**. Accept the normal Windows UAC prompt. Python, pip and a separate Tk installation are not required. Opening the app does not scan a disk.

Use **開啟示範（不讀硬碟）** on the recovery tab to preview the bundled synthetic photo and AVI. Supported video codecs play inside the app with pause/replay; unsupported formats can be opened in the system player. Codec support depends on Windows. The demo is artificial, not recovered user data.

Features: bounded read-only imaging, persistent REQUESTED/GOOD maps, skip uncertain requests on resume, SHA-256 checks, JPEG/PNG extraction and preview, native video preview, verified image export and conservative avoidance CSV. First new read anomaly stops the pass. Preserve more than 5 GB free. No automatic partition writing or physical bad-sector repair. The separately confirmed CHKDSK /f path changes the source filesystem and requires a complete verified physical-disk backup.

The executable is currently unsigned. Windows may show an unknown-publisher or reputation warning; no security settings should be disabled. UAC is requested for disk access. This is an experimental recovery tool, not a physical drive repair service. PhotoRec remains an optional official download placed beside the EXE at vendor/testdisk-7.2/photorec_win.exe.

- [Usage](docs/USAGE.en.md)
- [Feature comparison](docs/COMPARISON.en.md)
- [EXE validation / EXE驗證 / EXE検証](docs/EXE-VALIDATION.md)
- [MIT license](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)

UI: 繁體中文 / Traditional Chinese. Windows x64.

[Build from source / 從原始碼建置 / ソースからビルド](docs/BUILD.md)
