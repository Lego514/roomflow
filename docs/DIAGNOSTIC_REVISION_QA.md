# 診斷與居家案例驗證 / Diagnosis and incident verification

驗證日期：2026-10-12。這次修改收斂 `homenet` 的診斷結論，整理固定居家觀察快照，並同步文件。居家路由器改善仍待實際前後測。

## 自動測試

| 範圍 | 通過 |
|---|---:|
| Node 模型、session、server 與中英介面 | 29 |
| Python Linux lab | 19 |
| Python homenet | 78 |
| 合計 | 126 |

```sh
node --test --test-reporter=dot tests/*.test.mjs
python -B -m unittest discover -s lab -p 'test_*.py'
python -B -m unittest discover -s homenet/tests -t .
git diff --check
```

誤判回歸涵蓋第二跳的歸屬、目的地未確認／未回覆、孤立 ICMP 異常、IPv6 位址未取得／TCP 未成功／零樣本、歷史模糊資料及 CLI 報表。Windows SQLite handle 釋放也已驗證。

## 固定案例與圖表

- [去識別化快照](evidence/home-incident.json) 的截止時間為 `2026-10-12T06:05:02Z`，包含 1,238 次檢查。UTC 與 America/New_York 的 UTC-04:00 顯示明確記錄。
- 從現有資料庫以固定截止時間再次匯出，輸出與保存的 JSON 逐位元組相同。匯出採 SQLite `mode=ro`、`query_only` 和一致的讀取 transaction。
- 用 `homenet.episodes` 對快照 timeline 重算：3 個時段的起訖、214 次慢檢查、期間中位數與累計時長均吻合；generator SHA-256 也吻合。
- 核對 IPv6 的 run-level ANY-target 計數為慢時段 9/9、其他時段 0/46。這表示至少一個目標缺少 IPv6 成功觀察，保留歷史位址結果的不確定性。
- 快照通過 IPv4／MAC 位址格式掃描；匯出程式只保留白名單摘要與不公開映射的目標代號。
- 明／暗 SVG 從同一固定快照重產，XML 可解析；離線 raster preview 及文字邊界檢查通過。圖表標題與圖說呈現觀察，沒有排除 Wi-Fi 或宣稱已定位根因。

重算快照與圖表：

```sh
python -B scripts/export-home-incident.py --through 2026-10-12T06:05:02Z --output docs/evidence/home-incident.json
python -B scripts/plot-home.py docs/evidence/home-incident.json docs/
```

原始 SQLite 歷史保留在本機；只有持有該資料者可重跑匯出。其他讀者可從公開快照核對時間線與事件規則。匯出與本次驗證沒有執行新的網路探測或改動共用路由器。

[中文案例](home-incident.zh-TW.md) / [English case](home-incident.md) / [機器可讀驗證摘要](../artifacts/tests/diagnostic-revision.json)
