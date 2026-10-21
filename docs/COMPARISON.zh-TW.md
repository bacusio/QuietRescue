# 功能比較

| 工具 | 主要用途 | 恢復／修復能力 | QuietRescue的定位 |
|---|---|---|---|
| QuietRescue | Windows有限範圍鏡像GUI | 持久映射、雜湊、JPEG/PNG、選配PhotoRec、有門檻的CHKDSK入口 | Python程式碼可檢查，不重試規則明確；仍是硬體驗證有限的原型 |
| DiskGenius | 綜合磁碟、分區與資料恢復 | 檔案／分區恢復、克隆及壞道工具，依版本而異 | QuietRescue較精簡、容易核查流程，沒有證據表示恢復率或速度更高 |
| TestDisk／PhotoRec | 分區檔案系統分析與簽名提取 | TestDisk處理結構；PhotoRec提取多種格式，通常不能保留名稱／目錄 | QuietRescue外部呼叫PhotoRec，不能替代TestDisk的結構恢復 |
| GNU ddrescue | 使用mapfile的進階故障盤鏡像 | 斷點、多輪策略與可配置重試 | QuietRescue提供Windows照片導向UI，JSONL映射不相容ddrescue |
| 十六進位／二進位編輯器 | 手工檢視與修改位元組 | 可由專家定位結構與局部修改，依產品而異 | QuietRescue自動處理有限讀取與驗證，不是鑑識編輯器 |

QuietRescue適合需要可讀程式碼、清楚停止條件與本地照片預覽的人。重建檔案系統、處理大型故障盤策略或專業鑑識，仍需要專用工具。不重試可能犧牲部分原本可救的資料，是取捨而非絕對優勢。不能宣稱任何工具能讓物理介質恢復健康；避讓CSV也不等於修好了壞道。

## Sources / 來源 / 出典

Reviewed 2026-10-21. Features and licensing may change; this is not a recovery-rate or speed benchmark.

- [DiskGenius cloning](https://www.diskgenius.com/manual/clone-disk.php)
- [DiskGenius bad-sector checks and repair limitations](https://www.diskgenius.com/manual/verify-or-repair-bad-sectors.php)
- [TestDisk / PhotoRec overview](https://www.cgsecurity.org/testdisk_doc/index.html)
- [PhotoRec filename and filesystem limitations](https://www.cgsecurity.org/testdisk_doc/photorec.html)
- [GNU ddrescue manual](https://www.gnu.org/software/ddrescue/manual/ddrescue_manual.html)

Hex/binary editor is a category, not a specific tested product; capabilities vary by implementation.

## 獨立EXE版新增亮點

- 下載、解壓即可啟動一個EXE，不必裝Python。便攜是使用便利，並非本工具獨有，也不代表比DiskGenius更會救資料。
- 同一EXE包含受控讀取子程序，斷點續讀不再依賴已安裝的Python。
- 人工示範可直接看照片與內嵌影片，不必拿真實故障盤試功能。
- 請求映射、停止條件與雜湊驗證可檢查；但沒有證據證明恢復率、速度或硬體風險優於DiskGenius、ddrescue。
- DiskGenius的分區／檔案系統工具更全面；TestDisk可處理本工具沒有的結構恢復；PhotoRec處理更多格式；ddrescue有成熟的多輪策略。本版不能替代這些能力。

EXE實測涵蓋UAC管理員權限、人工映像分兩次續讀且請求不重複、照片逐位元組一致、AVI播放位置前進。未因此驗證全部影片編碼、故障硬體、物理修復或其他Windows版本。
