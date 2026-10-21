# 機能比較

| ツール | 主な用途 | 復旧・修復 | QuietRescueの位置づけ |
|---|---|---|---|
| QuietRescue | Windows向け範囲指定イメージGUI | 永続マップ、ハッシュ、JPEG/PNG、任意のPhotoRec、条件付きCHKDSK起動 | 読めるPythonコードと明示的な再試行禁止。ハードウェア検証の限られた試作品 |
| DiskGenius | 総合ディスク・パーティション管理と復旧 | ファイル／パーティション復旧、クローン、不良セクター関連機能。版により異なる | QuietRescueは範囲が狭く動作を追いやすい。復旧率・速度の優位性は未証明 |
| TestDisk / PhotoRec | 構造解析とシグネチャ抽出 | TestDiskは構造、PhotoRecは多形式抽出。通常は元の名前・階層を保持しない | QuietRescueはPhotoRecを外部起動し、TestDiskの構造復旧を代替しない |
| GNU ddrescue | mapfileを使う高度な救出イメージ作成 | 再開、複数パス、設定可能な再試行 | QuietRescueはWindowsの写真向けUI。JSONLマップはddrescue非互換 |
| 16進／バイナリエディター | バイトの手動閲覧・編集 | 専門家による構造調査や局所変更。製品に依存 | QuietRescueは範囲指定取得と検証を自動化するもので、鑑識エディターではない |

読みやすいコード、明確な停止条件、ローカル写真表示にはQuietRescueが適しています。ファイルシステム再構築、大規模障害ディスクの戦略、鑑識分析には専用ツールが必要です。再試行しない方針は救出可能なデータを取り逃す場合もあり、常に優れているとは限りません。物理メディアの健康回復は保証できず、回避CSVは不良セクター修理ではありません。

## Sources / 來源 / 出典

Reviewed 2026-10-21. Features and licensing may change; this is not a recovery-rate or speed benchmark.

- [DiskGenius cloning](https://www.diskgenius.com/manual/clone-disk.php)
- [DiskGenius bad-sector checks and repair limitations](https://www.diskgenius.com/manual/verify-or-repair-bad-sectors.php)
- [TestDisk / PhotoRec overview](https://www.cgsecurity.org/testdisk_doc/index.html)
- [PhotoRec filename and filesystem limitations](https://www.cgsecurity.org/testdisk_doc/photorec.html)
- [GNU ddrescue manual](https://www.gnu.org/software/ddrescue/manual/ddrescue_manual.html)

Hex/binary editor is a category, not a specific tested product; capabilities vary by implementation.

## EXE版で追加した利点

- ダウンロード、展開、EXE起動だけで使え、Pythonは不要です。ポータブルであることは利便性であり、独自性やDiskGeniusより高い復旧性能の証明ではありません。
- 同じEXEに制御された読み取りworkerが含まれ、再開時も外部Pythonに依存しません。
- 人工デモで写真と動画を確認でき、実際の障害ディスクを試験に使う必要がありません。
- 要求マップ、停止条件、ハッシュ検証を確認できます。ただしDiskGeniusやddrescueより高い復旧率、速度、低いハードウェアリスクは実証していません。
- DiskGeniusは分区・ファイルシステム機能が広く、TestDiskは未対応の構造復旧、PhotoRecは多数形式、ddrescueは成熟した複数パス戦略を提供します。それらを置き換える版ではありません。

EXE実測はUAC管理者権限、人工イメージの2回の再開と要求重複なし、写真のバイト一致、AVI再生位置の進行を対象としています。全コーデック、障害ハードウェア、物理修理、他のWindowsバージョンの検証ではありません。
