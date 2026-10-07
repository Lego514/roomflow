# 真實 Linux 網路實驗

這個 lab 用 Linux 核心的 network namespaces、veth、`tc` 與 `iperf3` 執行封包實驗。它與瀏覽器的數值模擬分開：只有執行 lab 後產生的 JSON/CSV 才是核心網路量測。所有流量留在虛擬機內，沒有更動家裡的路由器。

## 環境與安裝

在一次性 Ubuntu/Alpine 虛擬機內以 root 執行。需要 Python 3（僅標準函式庫）、完整 iproute2 的 `ip`/`tc`/`ss`、iperf3、iputils ping、ethtool。Windows 原生不能執行 Linux namespaces；WSL2 也要先確認核心功能，不能假設支援 CAKE。

Ubuntu 套件：

```sh
sudo apt-get update
sudo apt-get install python3 iproute2 iperf3 iputils-ping ethtool
```

Alpine 套件：

```sh
apk add python3 iproute2 iproute2-tc iperf3 iputils ethtool
```

核心需要 netns/veth、HTB、pfifo、netem、CAKE、flower classifier 與 skbedit action。腳本會在獨立、隨機名稱的 probe namespace 實際嘗試每項功能，缺少 CAKE 時直接失敗並列出原因，不會偷偷換成別的佇列管理機制。

```sh
python3 lab/test_netlab.py
sudo python3 lab/netlab.py check
sudo python3 lab/netlab.py setup --up-mbps 5 --down-mbps 20 --rtt-ms 40
sudo python3 lab/netlab.py status
```

## 拓樸

```text
meeting 10.77.1.2 ── router mlan 10.77.1.1
                              │
roommate 10.77.2.2 ─ router rlan 10.77.2.1
                              │
                        router wan 10.77.3.1
                       [共享上傳 5 Mbps]
                              │
                        delay torouter 10.77.3.2
                       [共享下載 20 Mbps]
                              │
                        delay toserver 10.77.4.1
                       [上傳 netem 延遲 20 ms]
                              │
                        server eth0 10.77.4.2
                       [下載 netem 延遲 20 ms]
```

兩個使用者通過同一個上傳瓶頸、同一個下載瓶頸；不是給每個使用者各一條獨立頻寬。下載的共用 shaper 位於受控制的虛擬 edge `delay/torouter` 上，因為 Linux egress qdisc 需要放在流量出站的一側。這是 ISP/router 鏈路的實驗抽象，實體路由器通常要以不同介面或 IFB 實作下載流量管理。

固定延遲放在獨立的另一段 veth，而非混入瓶頸的佇列。veth 的 GSO/GRO/TSO 已停用，避免 FIFO 的大型 offload 封包與 CAKE 的分割機制造成額外比較差異。

## 三種策略

| mode | 實作 | 容量 |
|---|---|---|
| `fifo` | 單一 HTB class + pfifo；FIFO buffer 約 300 ms | 同樣上傳 5 / 下載 20 Mbps |
| `sqm` | CAKE besteffort、方向相應的 host fairness | 同上 |
| `meeting` | CAKE diffserv4 + 受控制的裝置分類 | 同上 |

FIFO 使用 HTB、CAKE 使用自身 shaper，所以瞬時排程/突發與整體開銷會不同；公平比較保留相同的設定容量與流量需求，同時記錄實際吞吐量。這不是把限制頻寬前後當成兩種策略比較。

會議策略透過 CAKE 正式支援的 `skbedit priority` tin override 分類：

- 上傳必須同時符合 `src_ip 10.77.1.2` 與從 `mlan` 進入 router 的條件，才進入 Voice tin。
- 下載必須目的地是 `10.77.1.2`。
- 其他 IPv4 一律覆寫為 Best Effort tin，忽略使用者自己宣稱的 DSCP 高優先權。
- `wash` 清除出站 DSCP（保留 ECN），所有規則只存在 lab namespace。

選定整台裝置代表該裝置的所有 IPv4 流量都會優先，包括 ping。這個版本不辨識 Zoom/Teams，也不支援任意 IPv6 或 Wi-Fi 無線層排程。CAKE 的 Voice tin 有頻寬分享門檻，不是讓室友完全不能下載。

## 單次量測

```sh
sudo python3 lab/netlab.py run --mode fifo --scenario both --duration 15 --warmup 3 --output results/linux/fifo-both
sudo python3 lab/netlab.py run --mode sqm --scenario both --duration 15 --warmup 3 --output results/linux/sqm-both
sudo python3 lab/netlab.py run --mode meeting --scenario both --duration 15 --warmup 3 --output results/linux/meeting-both
```

每次實驗有兩條雙向即時流量替代品：每方向 600 Kbps UDP，payload 256 bytes。背景工作則是每方向四條 TCP 連線，試圖用滿容量。`idle` 沒有室友背景流量；`upload`/`download`/`both` 指背景流量方向。每條測試各有獨立 iperf3 server port，全部透過相同拓樸。

**UDP 替代流量不是 WebRTC。** 它沒有影音編碼、自適應 bitrate、重傳/FEC、會議服務的擁塞控制，也沒有實際聲音與畫面。量測只能證明這個受控瓶頸內的傳輸效果，不能宣稱真實會議一定不卡。之後應接入實際通話、真實 Wi-Fi 與路由器驗證。

每個新的輸出目錄保留：

- `metadata.json`：模式、容量、延遲、版本、暖機時間。
- `meeting-*.json`、`roommate-*.json` 與各自 `*-server.json`：iperf3 原始 JSON，連同 stderr。
- `ping.txt`：包含 timestamp 的原始 RTT；p95/mean 排除暖機期間。ping loss 明確標示包含暖機。
- `tc-before.json`、`tc-after.json`：真實 qdisc、filter、tin/action counter。
- `summary.json`：UDP receiver jitter/loss/throughput、TCP receiver throughput、RTT p95 與 CPU 使用率。

輸出目錄非空就拒絕覆寫。單一 CPU 平均 busy >85% 會標記警告；此時要檢查虛擬機資源，不能把 CPU 限制誤解為策略效果。

## 重複實驗與回歸測試

```sh
# 12 組策略/情境，加上核心設定、到期與服務重啟測試。
sudo python3 lab/netlab.py selftest --duration 8 --output results/linux/selftest

# 每個組合重複三次，固定 seed 打散順序，約 11 分鐘。
sudo python3 lab/netlab.py batch --duration 15 --repeats 3 --output results/linux/batch
```

`selftest` 會檢查每組是否有足夠 ping samples、UDP/TCP 接收量測，以及 selected/default 分類計數。在 meeting/both 情境，室友故意使用 CS6 DSCP；這仍必須有強制 Best Effort 計數。它也會操作**實際核心 qdisc**，驗證背景計時器自動恢復、提前結束及 timer service 停止後的到期 reconciliation。

`selftest` 沒有把「meeting 一定比 sqm 好」寫死當成通過條件：公平排隊本來就可能讓小型即時流量獲得足夠保護。比較結果應如實呈現。`batch.json` 包含每次 summary，`measurements.csv` 可供繪圖；未完成的 batch 會標示 `completed: false`，不冒充完成報告。

匯出原始資料後可另跑獨立稽核工具（不引用 netlab 的計算函式）：

```sh
python3 lab/audit_results.py --input results/linux/selftest --output results/linux/selftest-audit.json
python3 lab/audit_results.py --input results/linux/batch --output results/linux/batch-audit.json
```

它逐項比對 receiver `sum_received`、以 bytes/time 重算 throughput、以原始 timestamp ping 重算 p95，並核對工作負載、暖機、IPv4 端點、CAKE 設定與優先規則/tin 計數。預設稽核以完整 3 × 4 情境及 5/20 Mbps、40 ms 的標準實驗為範圍。iperf3 本身的 interval/end 計數差異與 UDP loss denominator 差異會保留為 observation，不能擅自修正或丟掉原始資料。

## 真實核心的限時模式

```sh
sudo python3 lab/netlab.py mode --mode sqm
sudo python3 lab/session.py start --seconds 60
sudo python3 lab/session.py status
sudo python3 lab/session.py stop
```

Session 保存原本的 `fifo`/`sqm` 模式、lab ownership token、到期時間，並將套用、恢復與失敗事件記入 `lab/.session-events.jsonl`。獨立 Python worker 在期限到達時套回原本模式並讀回確認。手動 stop 提前恢復；worker 中斷後，下一次 status/start 會恢復已過期的 session。恢復失敗會保留 active 紀錄，方便重試。重建 lab 後，舊 token 的 active session不能套用到新拓樸。

每次變更確認上、下載 qdisc、容量與分類規則；套用失敗嘗試回復前一個模式。兩個方向不是原子的核心交易，錯誤過程可能短暫留下部分更新，這會回報為失敗。請勿同時執行流量實驗與限時 session，或用第二個程式同時改 lab 的 qdisc。

## 清除與安全邊界

```sh
sudo python3 lab/session.py stop
sudo python3 lab/netlab.py teardown
```

Lab namespace 名稱固定為 `nc-lab-*`，每個介面都帶隨機 ownership alias。Setup 遇到同名 namespace 或既有狀態就拒絕建立。Teardown 先核對 ownership，且有任何存活程序就拒絕刪除；它不殺不認識的程序、不掃描並廣泛刪除 namespace，也不更動 host route/firewall/forwarding。測試只終止自己啟動且記錄的 process group。

若操作失敗，先閱讀 CLI error 與原始 stderr。不要直接刪除所有 namespaces。Ownership mismatch 時保留現場並人工檢查 `ip netns list`、`ip -n nc-lab-router -d link` 和 lab state。

## 技術來源

- [CAKE：shaper、host fairness、Diffserv、tc tin override](https://man7.org/linux/man-pages/man8/tc-cake.8.html)
- [Linux CAKE 實作](https://github.com/torvalds/linux/blob/master/net/sched/sch_cake.c)
- [tc flower 的 ingress interface/IP 分類](https://man7.org/linux/man-pages/man8/tc-flower.8.html)
- [netem 延遲與模擬限制](https://man7.org/linux/man-pages/man8/tc-netem.8.html)
- [iperf3 TCP/UDP、反向測試與 JSON](https://software.es.net/iperf/invoking.html)
