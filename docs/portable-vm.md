# 這台 Windows 上的隔離 Linux 測試環境

本次驗證使用專案內的可攜 QEMU 與 Alpine live ISO。沒有安裝 WSL、Docker、系統級 QEMU 或變更家用網路設定。虛擬機以軟體 TCG 執行，所有測試角色與流量位於同一個 Linux guest 的獨立 namespaces。

## 已保存的執行檔

`.runtime/` 不列入版本控制：

- QEMU 11.1.0 Windows build：官方 QEMU 下載頁指向的 Stefan Weil build。
- Alpine virt 3.24.2 live ISO、Linux 6.18.52-0-virt。
- 7-Zip 26.04 的 MSI 管理解壓檔案，僅用於解出 QEMU，沒有完成系統軟體安裝。
- 下載檔案、QEMU SHA-512 與 Alpine SHA-256；下載後均已與發布的 checksum 核對。

來源：[QEMU 下載頁](https://www.qemu.org/download/)、[Windows build](https://qemu.weilnetz.de/w64/)、[Alpine](https://alpinelinux.org/downloads/)、[7-Zip](https://www.7-zip.org/download.html)。

此 guest 使用 RAM 檔案系統；關機會清除 guest 內的套件與狀態。原始測量已匯出到專案 `results/linux/`，原始程式在 `lab/`，因此測量與實作不依赖存活的 VM。

## 再次執行

先在專案根目錄開兩個 PowerShell 終端。第一個啟動只監聽 loopback 的 artifact bridge：

```powershell
tar.exe -cf '.runtime\lab.tar' lab
node scripts/vm-files.mjs
```

第二個啟動隱藏的隔離 VM：

```powershell
.\scripts\start-vm.ps1
```

VM 的 serial TCP 只綁 `127.0.0.1:4546`；沒有 SSH 或對 LAN 的轉送。套件下載需要讓 QEMU 能連到官方 Alpine 套件庫。

讀取開機狀態，看到 `localhost login:` 後登入：

```powershell
node scripts/vm-serial.mjs '' 3000 raw
node scripts/vm-serial.mjs root 1000 raw
```

準備 guest。以下字串由 helper 傳入 guest shell，操作都發生在隔離 guest：

```powershell
node scripts/vm-serial.mjs 'ip link set eth0 up; udhcpc -i eth0 -q -n; printf "https://dl-cdn.alpinelinux.org/alpine/v3.24/main\nhttps://dl-cdn.alpinelinux.org/alpine/v3.24/community\n" > /etc/apk/repositories; apk add python3 iproute2 iproute2-tc iperf3 iputils ethtool curl' 30000
node scripts/vm-serial.mjs 'mkdir -p /root/roomflow; wget -q -O /root/lab.tar http://10.0.2.2:3211/lab.tar; tar -xf /root/lab.tar -C /root/roomflow; cd /root/roomflow; python3 lab/netlab.py check' 20000
node scripts/vm-serial.mjs 'cd /root/roomflow; python3 lab/netlab.py setup' 20000
```

執行實驗時讓 helper 的時間足夠涵蓋整個操作，或將 guest 作業放到背景，將 stdout/stderr 與退出碼保存為檔案後另外查詢。Helper 逾時只會斷開 serial，**不會**把仍在 guest 執行的實驗標為成功或停止它。

```powershell
node scripts/vm-serial.mjs 'cd /root/roomflow; python3 lab/netlab.py run --mode sqm --scenario both --duration 15 --warmup 3 --output results/linux/new-sqm-both' 30000
```

更多策略、自我測試與矩陣命令見 [Linux lab](linux-lab.md)。不可覆寫非空的原始結果目錄。

本次完整 batch 後另執行補充診斷，原始 batch 保留。`lab/run-diagnostic.sh` 執行 SQM idle 起點、三輪輪換順序的 FIFO／SQM／meeting 混合負載、SQM idle 終點，共 11 次；前後另外記錄 clocksource、100 次 10 ms sleep 的實際等待、CPU／softirq／softnet／interrupt 計數。此腳本拒絕覆寫已存在的目錄：

```sh
bash lab/run-diagnostic.sh results/linux/new-diagnostic
```

在獨立輸出中保留結果。它是針對本次運行波動的診斷，沒有修改作業系統 timer、電源設定或 AQM 參數，也不能取代完整四情境矩陣。

## 匯出測量與清理

將這次 guest 的 `results/` 打包，經 loopback bridge 存回專案 `.runtime/linux-results.tar`：

```powershell
node scripts/vm-serial.mjs 'cd /root/roomflow; tar -cf /root/export.tar results; curl --fail -sS -X PUT --data-binary @/root/export.tar http://10.0.2.2:3211/results.tar' 15000
tar.exe -tf '.runtime\linux-results.tar'
```

先查看 tar 內容，再解壓到新的目錄以保留舊測量。此 bridge 只接受 `/lab.tar` 讀取與 `/results.tar` 寫入，沒有任意檔案 API。

測試結束後：

```powershell
node scripts/vm-serial.mjs 'cd /root/roomflow; python3 lab/session.py stop; python3 lab/netlab.py teardown' 20000
node scripts/vm-serial.mjs poweroff 5000 raw
```

關閉第一個終端的 bridge。Web dashboard 的 Node 服務與 VM 分開，可以繼續讀取保存的 Linux 報告。
