# QuietRescue 1.1 — Windows ポータブル EXE

[English](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

Windows-x64 ZIPをローカルフォルダーに展開し、**QuietRescue.exe**をダブルクリックして通常のWindows UACを許可してください。Python、pip、Tkの別途インストールは不要です。起動しただけではディスクをスキャンしません。

復元タブの「開啟示範（不讀硬碟）」から、同梱の人工写真とAVI動画を表示できます。対応コーデックはアプリ内で再生・一時停止・再再生できます。非対応形式はシステムプレーヤーで開けます。コーデック対応はWindowsに依存し、デモは復旧した個人データではありません。

範囲指定の読み取り専用イメージ、永続REQUESTED/GOODマップ、結果不明要求の除外再開、SHA-256検証、JPEG/PNG抽出・プレビュー、動画の内蔵再生、検証済みイメージと保守的な回避CSVの出力に対応します。最初の新規異常で停止し、5GB超を残します。自動パーティション書き込みや物理不良セクター修理は行いません。CHKDSK /fは別途確認する元ディスクへの書き込みで、完全な検証済み物理ディスクバックアップが必要です。

EXEは現在未署名です。Windowsで不明な発行元や評価の警告が出る場合がありますが、セキュリティ設定を無効にしないでください。UACはディスクアクセス用です。物理ドライブを修理するツールではありません。PhotoRecは任意の公式ダウンロードで、EXEの隣のvendor/testdisk-7.2/photorec_win.exeに配置します。

- [使い方](docs/USAGE.ja.md)
- [機能比較](docs/COMPARISON.ja.md)
- [EXE validation / EXE驗證 / EXE検証](docs/EXE-VALIDATION.md)
- [MIT license](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)

UI: 繁體中文 / Traditional Chinese. Windows x64.

[Build from source / 從原始碼建置 / ソースからビルド](docs/BUILD.md)
