## Kernel lab results

Profile home: 35/250 Mbps up/down, 25 ms base RTT, FIFO queue 180 ms. GitHub Actions ubuntu-24.04, run 37885930240, seed 20261007. 60 runs, 5 per cell. p95 RTT is the mean of per-run p95 values (range of single runs in brackets).

| Scenario | Policy | Meeting p95 RTT ms | Meeting loss % up / down | Meeting jitter ms up / down | Roommate Mbps up / down |
|---|---|---:|---:|---:|---:|
| idle | fifo | 25.1 (25.1–25.1) | 0.00 / 0.00 | 0.02 / 0.00 | — / — |
| idle | sqm | 25.1 (25.1–25.2) | 0.00 / 0.00 | 0.10 / 0.00 | — / — |
| idle | meeting | 25.2 (25.1–25.2) | 0.00 / 0.00 | 0.01 / 0.00 | — / — |
| upload | fifo | 191.8 (191.0–192.0) | 0.13 / 0.00 | 0.99 / 0.04 | 32.94 / — |
| upload | sqm | 25.6 (25.5–25.7) | 0.00 / 0.00 | 0.27 / 0.03 | 31.64 / — |
| upload | meeting | 25.5 (25.4–25.5) | 0.00 / 0.00 | 0.27 / 0.04 | 31.65 / — |
| download | fifo | 202.4 (202.0–203.0) | 0.00 / 0.18 | 0.31 / 0.14 | — / 238.77 |
| download | sqm | 25.4 (25.4–25.4) | 0.00 / 0.00 | 0.18 / 0.09 | — / 224.23 |
| download | meeting | 25.4 (25.3–25.4) | 0.00 / 0.00 | 0.20 / 0.10 | — / 222.87 |
| both | fifo | 196.4 (195.0–198.0) | 2.30 / 0.09 | 4.07 / 3.50 | 20.52 / 237.49 |
| both | sqm | 25.8 (25.8–25.9) | 0.00 / 0.00 | 0.30 / 0.11 | 26.63 / 227.62 |
| both | meeting | 25.6 (25.6–25.6) | 0.00 / 0.00 | 0.18 / 0.09 | 26.63 / 226.84 |

