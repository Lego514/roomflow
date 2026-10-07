# Deterministic model experiment

Engine: discrete-event queue/transport model. These are generated packet-event results, **not Linux CAKE or measured household Wi-Fi data**.

Configuration: 20 Mbps download, 5 Mbps upload, 40 ms base RTT; 60 seconds per run; 5-second warmup; seeds 42–44; 3 repetitions; 36 runs total. Paired policies use the same seed, and policy order rotates.

Table cells average per-run summaries. RTT is the mean of per-run p95 values, not a pooled percentile. Throughput columns combine both directions.

| Scenario | Policy | p95 RTT ms | Jitter ms | Meeting loss % | Meeting Mbps | Background Mbps |
|---|---|---:|---:|---:|---:|---:|
| idle | fifo | 41.85 | 0.00 | 0.000 | 2.50 | 0.00 |
| idle | fair | 41.85 | 0.00 | 0.000 | 2.50 | 0.00 |
| idle | priority | 41.85 | 0.00 | 0.000 | 2.50 | 0.00 |
| upload | fifo | 239.68 | 0.55 | 0.414 | 2.49 | 4.00 |
| upload | fair | 47.35 | 0.73 | 0.000 | 2.50 | 3.98 |
| upload | priority | 45.92 | 0.66 | 0.000 | 2.50 | 3.98 |
| download | fifo | 239.29 | 0.16 | 0.065 | 2.50 | 18.50 |
| download | fair | 42.74 | 0.50 | 0.000 | 2.50 | 18.45 |
| download | priority | 42.65 | 0.49 | 0.000 | 2.50 | 18.44 |
| mixed | fifo | 430.32 | 0.72 | 0.510 | 2.49 | 22.50 |
| mixed | fair | 48.51 | 1.23 | 0.000 | 2.50 | 22.42 |
| mixed | priority | 47.42 | 1.17 | 0.000 | 2.50 | 22.41 |

Raw packet/probe timestamps, configuration, samples, and byte-accounting counters are retained in each compressed JSON file. See docs/simulator.md for assumptions. UDP demand approximates a meeting transport; it cannot establish actual WebRTC quality. General fair queuing may be sufficient; meeting priority must be justified by its incremental benefit, not assumed.
