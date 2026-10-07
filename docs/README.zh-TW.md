# RoomFlow 中文說明

[English README](../README.md)

把「室友大量傳檔時，我的會議連線能否更穩？」變成可重現、可量測的網路實驗。

A reproducible networking project that asks: “Can my meeting connection stay responsive while my roommate transfers large files?” The dashboard offers Traditional Chinese and English; an English usage guide follows the Chinese guide below.

專案包含兩個清楚分開的執行環境：

- **Windows 可直接使用的模型介面**：封包事件、共用瓶頸、公平排隊與有限優先權由 Node.js 計算。這不是 Linux CAKE，也不會修改家裡的路由器。
- **Linux 實際封包 lab**：network namespaces、veth、tc、CAKE、netem、iperf3 與 ping，真實交換封包並留下核心佇列與接收端紀錄。這是虛擬拓樸的核心實測，仍不是實體 Wi-Fi 或 Zoom/Teams 品質驗證。

## 開啟介面

需要 Node.js 22 或以上。使用內建模組，不需要 npm install。

```powershell
cd 'C:\dev\NETWORK APP'
node src/server.mjs
```

開啟 <http://127.0.0.1:3210>。服務只綁定 loopback。

右上角可切換「繁體中文／English」，會保存這台瀏覽器的選擇。切換時保留目前的倒數、輸入條件與已顯示報告；原始 JSON／CSV 欄位和數值不隨語言改變。

1. 選擇「室友正在上傳、下載或同時傳輸」與頻寬。
2. 執行三策略對照，等待實驗完成。
3. 比較延遲、抖動、丟包及室友吞吐量；下載 CSV 或完整 JSON。
4. 使用「10 秒自動恢復測試」驗證計時模式。伺服器讀回設定後才顯示成功，到期回到公平排隊。
5. 下方「保存的 Linux 封包實測」可切換四種負載，查看已保存的三次重複量測及下載 CSV。這份實測不會隨 Web 計時卡片重新執行。

計時卡片中的「目前策略快照」會按照目前策略重新計算一個固定混合負載模型。它不是即時網路量測。完整對照實驗永遠固定比較 FIFO、公平排隊與優先排隊，不會被計時卡片改變。

狀態與實驗紀錄保存在 `data/`；到期時間會持久化，服務重啟後會重新套用有效策略或恢復已到期的策略。中途被服務重啟打斷的實驗會標記失敗，完成的報告仍可讀取。

## 驗證與重現

```powershell
node --test tests/*.test.mjs
node scripts/run-matrix.mjs
```

矩陣包含四個負載情境、三個策略、三次不同啟動相位，共 36 次模型實驗。原始封包時間戳、探測、守恆計數與樣本保存在 `results/model/*.json.gz`。摘要為每次實驗指標的平均；p95 欄位是各次 p95 的平均，不是合併後的 p95。

Linux 的純 Python 回歸測試：

```sh
python3 -m unittest discover -s lab -p 'test_*.py' -v
```

真正的 Linux lab 需要在可處理核心網路功能的隔離 Linux VM 中執行：

```sh
sudo python3 lab/netlab.py check
sudo python3 lab/netlab.py setup
sudo python3 lab/netlab.py selftest --duration 8 --output results/linux/selftest
sudo python3 lab/netlab.py batch --duration 15 --repeats 3 --output results/linux/batch
sudo python3 lab/netlab.py teardown
```

實際 Linux 限時控制另有 `lab/session.py start --seconds 60`、`status` 與 `stop`。它會變更隔離拓樸內的實際 qdisc，到期由獨立監督程序恢復原策略。Web 介面的計時示範與 Linux 控制器互相獨立。

## 結果與設計文件

- [完整驗證報告](../TEST_REPORT.md)
- [中英介面檢查](BILINGUAL_QA.md)
- [模型實驗數據](../results/model/REPORT.md)／[資料核對](../results/model/AUDIT.md)
- [Linux 實際封包結果](../results/linux/REPORT.md)／[原始資料稽核](../results/linux/BATCH_AUDIT.md)
- [模型的假設與量測定義](simulator.md)
- [Linux lab 的拓樸、前置條件與操作方式](linux-lab.md)
- [這台 Windows 的可攜 VM 重現方式](portable-vm.md)

Linux 原始資料放在 `results/linux/`，與模型資料分開保存。`artifacts/screenshots/` 保留桌面及手機版的操作畫面。

本次 Linux 矩陣後段與另存的 11 次補測出現持續的延遲／丟包波動，包含 idle；資料稽核通過，但異常原因未確定。功能檢查與效能穩定性分開報告，目前不能宣稱會議分類一定比一般 SQM 更好。詳見完整驗證及原始資料稽核。

## 第一版的界線

UDP 流量是會議傳輸的替代負載，沒有模擬完整 WebRTC 編碼、自適應碼率或影音體感。對照重點是排程與壅塞，不包含 Wi-Fi 訊號弱、ISP 斷線或服務端故障。

公平排隊可能已足夠；優先模式需要展示相對於公平排隊的額外價值。每個結果也保留室友的吞吐量，避免只看會議改善。待路由器型號及管理方式確認後，再設計居家實測與設備 adapter。
