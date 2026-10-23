> Latest: QuietRescue 1.2.2 prerelease. See [release notes and package setup](docs/RELEASE-1.2.2.md). The notes below may describe earlier versions.

# QuietRescue 1.2.1 — Windows x64

[English](README.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

Windows-x64 ZIPをローカルフォルダーに展開し、**QuietRescue.exe**をダブルクリックして通常のWindows UACを許可してください。Python、pip、Tkの別途インストールは不要です。起動しただけではディスクをスキャンしません。

1.1にあった読み取り専用の物理ディスクリーダーを復元し、1.2の計画レビュー、除外マップ、チェックポイント検証、進捗帯を維持しました。実際の読み取りには対象計画を確認して明示的に承認する必要があります。ソーステストは合成データのみで、故障した実ディスク上の読取・I/Oキャンセルは検証していません。

鏡像タブにはバイト位置の進捗帯を追加しました。`disk-rescue-progress/v1` JSONを選択すると、保存済み・報告済み・未確認・エラー・スキップ・未読・回避案を5秒ごとに更新します。青いカーソルをドラッグすると開始バイト欄に反映されます。シリアル番号と容量が完全一致する場合のみ地図を表示し、JSONだけを読み取ってディスクI/Oは開始しません。

復元タブの「開啟示範（不讀硬碟）」から、同梱の人工写真とAVI動画を表示できます。対応コーデックはアプリ内で再生・一時停止・再再生できます。非対応形式はシステムプレーヤーで開けます。コーデック対応はWindowsに依存し、デモは復旧した個人データではありません。

範囲指定の読み取り専用イメージ、永続REQUESTED/GOODマップ、結果不明要求の除外再開、SHA-256検証、JPEG/PNG抽出・プレビュー、動画の内蔵再生、検証済みイメージと保守的な回避CSVの出力に対応します。最初の新規異常で停止し、5GB超を残します。自動パーティション書き込みや物理不良セクター修理は行いません。故障ディスクでのI/Oキャンセル動作は未検証のため、故障ディスクの動作は保証しません。

EXEは現在未署名です。Windowsで不明な発行元や評価の警告が出る場合がありますが、セキュリティ設定を無効にしないでください。UACはディスクアクセス用です。物理ドライブを修理するツールではありません。PhotoRecは任意の公式ダウンロードで、EXEの隣のvendor/testdisk-7.2/photorec_win.exeに配置します。

- [使い方](docs/USAGE.ja.md)
- [機能比較](docs/COMPARISON.ja.md)
- [EXE validation / EXE驗證 / EXE検証](docs/EXE-VALIDATION.md)
- [MIT license](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)

UI: 繁體中文 / Traditional Chinese. Windows x64.

[Build from source / 從原始碼建置 / ソースからビルド](docs/BUILD.md)
