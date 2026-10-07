# Model result audit

Generated with `node scripts/run-matrix.mjs` and independently checked by reading every compressed JSON record.

- 36 runs: four scenarios × three policies × three startup seeds.
- 2,160 interval samples, 562,500 raw meeting packet records and 21,600 raw probe records.
- No missing RTT bins in this matrix.
- All offered packet/byte counters equal delivered plus dropped after drain.
- All queues remain within their byte budgets and finish empty.
- All serialized bytes remain below directional capacity × elapsed time.
- All measured interval media-byte totals reproduce the published summary rates.
- Simulator unit tests: 12 passed; duration input accepts the dashboard's maximum 180 seconds and rejects 181 seconds.

## Observed findings

For mixed upload/download congestion, the averages of each run's p95 RTT are **430.32 ms FIFO, 48.51 ms fair, 47.42 ms priority**. Meeting loss is **0.510%, 0%, 0%** respectively. Combined background throughput is **22.50, 22.42, 22.41 Mbps**. The latter adds upload and download and must not be compared to a single 20 Mbps download link.

Fair queuing provides almost all of the RTT improvement; priority adds approximately **1.09 ms** in this particular model configuration. This supports considering fair queuing sufficient here, not assuming priority is essential.

Mixed-case mean absolute transit variation (“meeting jitter”) is **0.72 ms FIFO, 1.23 ms fair, 1.17 ms priority**. FIFO's large queue remains relatively steady, so its jitter can be lower even though its latency is much worse. The generated measurements do not support a claim that every indicator improves.

These are deterministic packet-event model results with different startup phases, not physical Wi-Fi measurements, actual Linux CAKE results, or statistical confidence intervals for household networks. See `docs/simulator.md` for the model and measurement definitions.
