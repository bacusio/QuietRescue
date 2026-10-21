# QuietRescue 1.1 — Windows 免安裝 EXE

[English](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

下載 Windows-x64 ZIP，完整解壓到本機資料夾，雙擊 **QuietRescue.exe** 並允許正常的 Windows UAC。使用者不需要安裝 Python、pip 或 Tk。開啟程式不會自動掃描硬碟。

在還原頁點「開啟示範（不讀硬碟）」，即可預覽內附人工照片與AVI影片。支援的編碼可內嵌播放、暫停與重播；不支援的格式可交給系統播放器。編碼支援取決於Windows，示範檔不是使用者救回的資料。

功能包含有限範圍只讀鏡像、REQUESTED/GOOD持久映射、續讀跳過未確認請求、SHA-256驗證、JPEG/PNG提取與預覽、內嵌影片預覽、已驗證映像匯出及保守避讓CSV。首次新增讀取異常即停，保留超過5GB空間。不自動寫分區表或修復物理壞道。CHKDSK /f是另行確認的來源寫入功能，須有完整已驗證物理硬碟備份。

EXE目前未簽署，Windows可能顯示未知發行者或信譽提示；不應停用系統安全設定。UAC用於硬碟存取。本工具仍是資料搶救原型，不能修復物理盤體。PhotoRec維持選配，請從官方下載後放到EXE旁的vendor/testdisk-7.2/photorec_win.exe。

- [使用說明](docs/USAGE.zh-TW.md)
- [功能比較](docs/COMPARISON.zh-TW.md)
- [EXE validation / EXE驗證 / EXE検証](docs/EXE-VALIDATION.md)
- [MIT license](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)

UI: 繁體中文 / Traditional Chinese. Windows x64.

[Build from source / 從原始碼建置 / ソースからビルド](docs/BUILD.md)
