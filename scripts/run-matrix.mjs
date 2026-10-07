import fs from 'node:fs';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import { simulate } from '../src/simulator.mjs';
import { POLICIES, SCENARIOS, summarizeRuns, resultCsv } from '../src/experiment.mjs';

const out = path.resolve(process.argv[2] ?? 'results/model');
fs.mkdirSync(out, { recursive: true });
const summaries = [], ledger = [];
const config = { durationSeconds:60, repeats:3, seed:42, upMbps:5, downMbps:20, baseRttMs:40 };
for (const scenario of SCENARIOS) {
  const runs = [];
  for (let repeat = 0; repeat < config.repeats; repeat++) {
    const order = POLICIES.slice(repeat % 3).concat(POLICIES.slice(0, repeat % 3));
    for (const policy of order) {
      const started = performance.now();
      const run = simulate({ ...config, scenario, mode:policy, seed:config.seed+repeat, warmupSeconds:5, sampleIntervalMs:1000 });
      const record = { ...run, policy, repeat:repeat+1 };
      runs.push(record);
      const name = `${scenario}-${policy}-${repeat+1}.json.gz`;
      fs.writeFileSync(path.join(out,name), gzipSync(JSON.stringify(record)));
      ledger.push({ file:name,scenario,policy,repeat:repeat+1,elapsedMs:performance.now()-started,summary:run.summary });
      console.log(`${scenario} ${policy} #${repeat+1}: p95=${run.summary.rttP95Ms.toFixed(1)}ms loss=${run.summary.meetingLossPct.toFixed(3)}% background=${run.summary.roommateThroughputMbps.toFixed(2)}Mbps`);
    }
  }
  summaries.push(...summarizeRuns(runs,scenario));
  fs.writeFileSync(path.join(out,`${scenario}.csv`), resultCsv({config:{...config,scenario},runs}));
}
fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify({engine:'discrete-event-model',config,summaries,ledger},null,2));
const rows = summaries.map(s => `| ${s.scenario} | ${s.policy} | ${s.meetingRttP95Ms.toFixed(2)} | ${s.meetingJitterMs.toFixed(2)} | ${s.meetingLossPct.toFixed(3)} | ${s.meetingMbps.toFixed(2)} | ${s.backgroundMbps.toFixed(2)} |`).join('\n');
fs.writeFileSync(path.join(out,'REPORT.md'), `# Deterministic model experiment\n\nEngine: discrete-event queue/transport model. These are generated packet-event results, **not Linux CAKE or measured household Wi-Fi data**.\n\nConfiguration: 20 Mbps download, 5 Mbps upload, 40 ms base RTT; 60 seconds per run; 5-second warmup; seeds 42–44; 3 repetitions; 36 runs total. Paired policies use the same seed, and policy order rotates.\n\nTable cells average per-run summaries. RTT is the mean of per-run p95 values, not a pooled percentile. Throughput columns combine both directions.\n\n| Scenario | Policy | p95 RTT ms | Jitter ms | Meeting loss % | Meeting Mbps | Background Mbps |\n|---|---|---:|---:|---:|---:|---:|\n${rows}\n\nRaw packet/probe timestamps, configuration, samples, and byte-accounting counters are retained in each compressed JSON file. See docs/simulator.md for assumptions. UDP demand approximates a meeting transport; it cannot establish actual WebRTC quality. General fair queuing may be sufficient; meeting priority must be justified by its incremental benefit, not assumed.\n`);
console.log(`Saved 36 raw runs and report to ${out}`);
