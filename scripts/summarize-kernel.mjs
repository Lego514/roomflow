import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';

const root = path.resolve(process.argv[2] ?? 'results/linux');
const batch = JSON.parse(fs.readFileSync(path.join(root,'batch','batch.json'),'utf8'));
const selftest = JSON.parse(fs.readFileSync(path.join(root,'selftest','selftest.json'),'utf8'));
if (!batch.completed || !selftest.passed || batch.measurements.length !== batch.repeats * 12) {
  throw new Error('Incomplete kernel evidence; refusing to publish a verified report.');
}
const policies = ['fifo','sqm','meeting'];
const scenarios = ['idle','upload','download','both'];
const summary = [];
const warnings = [];
const mean = values => values.length && values.every(v => typeof v === 'number' && Number.isFinite(v))
  ? values.reduce((a,b)=>a+b,0)/values.length : null;
for(const scenario of scenarios) for(const policy of policies) {
  const runs = batch.measurements.filter(item=>item.mode===policy || item.summary.mode===policy)
    .filter(item=>item.summary.scenario===scenario).map(item=>item.summary);
  if(runs.length !== batch.repeats) throw new Error(`Missing repetitions: ${policy}/${scenario}`);
  const flow = (name,field) => runs.map(run => {
    if(!run.flows[name] && name.startsWith('roommate')) return 0;
    return run.flows[name]?.[field];
  });
  const rtts=runs.map(run=>run.rtt.p95_ms);
  if(rtts.some(value=>value===null)) warnings.push(`${policy}/${scenario} has missing RTT samples.`);
  for(const run of runs) if(run.cpu_warning) warnings.push(`${policy}/${scenario}: CPU saturation warning.`);
  const mbps = values => { const v=mean(values);return v===null?null:v/1e6; };
  summary.push({policy,scenario,repeats:runs.length,rttP95MeanMs:mean(rtts),
    rttP95MinMs:rtts.every(Number.isFinite)?Math.min(...rtts):null,rttP95MaxMs:rtts.every(Number.isFinite)?Math.max(...rtts):null,
    meetingUpLossMeanPct:mean(flow('meeting-up','lost_percent')),meetingDownLossMeanPct:mean(flow('meeting-down','lost_percent')),
    meetingUpJitterMeanMs:mean(flow('meeting-up','jitter_ms')),meetingDownJitterMeanMs:mean(flow('meeting-down','jitter_ms')),
    meetingUpMeanMbps:mbps(flow('meeting-up','bits_per_second')),meetingDownMeanMbps:mbps(flow('meeting-down','bits_per_second')),
    backgroundUpMeanMbps:mbps(flow('roommate-up','bits_per_second')),backgroundDownMeanMbps:mbps(flow('roommate-down','bits_per_second'))});
}
const both=policy=>summary.find(row=>row.scenario==='both'&&row.policy===policy);
const fifo=both('fifo'),sqm=both('sqm'),meeting=both('meeting');
const f=value=>Number.isFinite(value)?value.toFixed(2):'—';
const extra=Number.isFinite(sqm.rttP95MeanMs)&&Number.isFinite(meeting.rttP95MeanMs)
  ?sqm.rttP95MeanMs-meeting.rttP95MeanMs:null;
const findings=[
  `雙向壅塞的 p95 RTT 平均：FIFO ${f(fifo.rttP95MeanMs)} ms、SQM ${f(sqm.rttP95MeanMs)} ms、會議優先 ${f(meeting.rttP95MeanMs)} ms。`,
  extra===null?'存在無有效 RTT 的實驗，無法比較會議優先與 SQM 的 p95 增益。'
    :`會議優先相對 SQM 的 p95 平均${extra>=0?'降低':'增加'} ${f(Math.abs(extra))} ms；請同時查看三次測量範圍，這不是統計顯著性或通話體感的結論。`,
  '延遲統計來自選定會議裝置的 ping；丟包、抖動及吞吐量來自 iperf3 接收端，沒有以預設數字填入。',
  '上傳與下載的吞吐量分開顯示；每次實驗先暖機 3 秒，再量測 15 秒。',
  '這批測量後段出現持續的 RTT、丟包與吞吐量波動，包含沒有室友背景流量的情境；原始結果全部保留。資料已核對，但異常原因尚未確定，不能將這批平均值解讀成真實家庭網路的效能保證。',
  '另存的 11 次診斷補測仍出現延遲與丟包；目前沒有足夠證據證明會議分類比一般 SQM 有穩定額外收益。',
];
const hashes={};
for(const name of ['batch/batch.json','batch/measurements.csv','selftest/selftest.json']) {
  hashes[name]=createHash('sha256').update(fs.readFileSync(path.join(root,name))).digest('hex');
}
const first=batch.measurements[0].summary;
const evidence={status:'verified',engine:'linux-kernel',environment:{kernel:first.kernel,hypervisor:'QEMU TCG',
  upMbps:first.up_mbps,downMbps:first.down_mbps,baseRttMs:first.base_rtt_ms,durationSeconds:first.duration_seconds,
  warmupSeconds:first.warmup_seconds,repeats:batch.repeats,runCount:batch.measurements.length,
  selftestChecks:selftest.checks.filter(check=>check.ok===true).length},summary,findings,warnings,hashes,
  rawCsvUrl:'/api/kernel-evidence/export.csv'};
fs.writeFileSync(path.join(root,'summary.json'),JSON.stringify(evidence,null,2)+'\n');
const rows=summary.map(row=>`| ${row.scenario} | ${row.policy} | ${f(row.rttP95MeanMs)} (${f(row.rttP95MinMs)}–${f(row.rttP95MaxMs)}) | ${f(row.meetingUpLossMeanPct)} / ${f(row.meetingDownLossMeanPct)} | ${f(row.meetingUpJitterMeanMs)} / ${f(row.meetingDownJitterMeanMs)} | ${f(row.backgroundUpMeanMbps)} / ${f(row.backgroundDownMeanMbps)} |`).join('\n');
fs.writeFileSync(path.join(root,'REPORT.md'),`# Linux 封包實測報告\n\n環境：QEMU TCG、Alpine Linux、核心 ${first.kernel}。使用實際 network namespaces、veth、tc HTB/FIFO、CAKE、netem 與 iperf3；不是 Web 介面的數值模型，也不是實體 Wi-Fi。\n\n共用容量：下載 ${first.down_mbps} Mbps、上傳 ${first.up_mbps} Mbps；基礎 RTT ${first.base_rtt_ms} ms。會議替代流量每方向 600 Kbps UDP、256-byte payload，背景為每方向四條 TCP 連線。每次暖機 ${first.warmup_seconds} 秒、量測 ${first.duration_seconds} 秒，四情境 × 三策略 × 三次，共 ${batch.measurements.length} 次；執行順序以 seed 22756 隨機打散。所有策略保持相同頻寬預算，GSO/GRO/TSO 關閉。\n\n${findings.map(text=>'- '+text).join('\n')}\n\n| 情境 | 策略 | p95 RTT 平均 ms（單次範圍） | 會議丟包 % 上／下 | 會議 jitter ms 上／下 | 室友 Mbps 上／下 |\n|---|---|---:|---:|---:|---:|\n${rows}\n\n表格是三次單次摘要的平均；p95 是各次 p95 的平均，不是合併百分位。RTT 依 ping 時間戳排除暖機；iperf 指標採用接收端自己的摘要。保留原始 loss%，不把 packets 欄位重新解釋成其分母。\n\n自我測試：${evidence.environment.selftestChecks} 項通過，包含 12 個策略／負載組合、未授權 DSCP 優先權抑制、獨立計時程序恢復、到期重啟 reconciliation、提前結束。見 selftest/selftest.json 與 session-events.jsonl。\n\nCPU 警告：${warnings.length?warnings.join('; '):'沒有任何測試觸發單一 vCPU 平均忙碌率 >85% 的警告。這不排除短暫排程抖動或 TCG 對測量的影響。'}\n\n原始資料：batch/ 下每次的 iperf client/server JSON、ping 時間戳、qdisc/classification 計數、metadata 與 summary；batch/measurements.csv 與 batch/batch.json 保存全部結果。關鍵檔案 SHA-256 保存在 summary.json。\n\n此實驗不模擬完整 WebRTC 或真實無線訊號。三次短測不足以代表家庭網路或建立統計顯著性；優先模式是否有增益應依結果及不同流量條件判斷。模型與核心實测的 UDP 負載、抖動定義不同，不能直接把兩者數值當成同一量測相互比較。\n`);
console.log(JSON.stringify({runCount:evidence.environment.runCount,both:[fifo,sqm,meeting],warnings},null,2));
