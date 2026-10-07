# RoomFlow

**Can my video call stay usable while my roommate uploads and downloads large files on the same connection?**

RoomFlow answers that with real packets: a Linux lab that shares one bottleneck between a "meeting" device and a "roommate" device, then compares three queueing policies under the same bandwidth.

[中文說明](docs/README.zh-TW.md)

## Finding

The problem is **bufferbloat**, and fair queuing fixes most of it. Prioritizing the meeting device on top of that made no measurable difference.

Both directions congested (5 Mbps up / 20 Mbps down, 40 ms base RTT), three runs per policy on the Linux kernel lab:

| Policy | Meeting p95 RTT, mean (range) | Meeting loss up / down | Roommate throughput up / down |
|---|---:|---:|---:|
| FIFO (a plain router queue) | 290 ms (287–296) | 2.5% / 0.2% | 3.6 / 18.3 Mbps |
| CAKE SQM (fair queuing + AQM) | 63 ms (48–93) | 8.6% / 8.7% | 3.1 / 11.6 Mbps |
| CAKE + meeting priority | 62 ms (48–91) | 0% / 3.8% | 3.0 / 11.0 Mbps |

- **FIFO lets the bulk transfers fill the buffer**, so every meeting packet waits behind them: p95 latency goes from 40 ms to about 290 ms.
- **CAKE keeps the queue short** and shares the link fairly: most runs sat near 48 ms.
- **Meeting priority vs plain CAKE:** 62 vs 63 ms, with overlapping ranges. No evidence it helps. It does trade the roommate's throughput, which is reported next to every result.

**These numbers are provisional.** The kernel lab ran inside QEMU with software CPU emulation (TCG), whose timing is unreliable: later runs drifted, and even idle runs under CAKE showed loss that a native kernel shouldn't. The FIFO-vs-CAKE gap is large enough to survive that noise; the smaller differences are not. The next step is rerunning on a native Linux kernel. Every raw result is kept, including the anomalous runs; see [the verification report](TEST_REPORT.md) and [the raw-data audit](results/linux/BATCH_AUDIT.md).

## How it works

```
meeting  10.77.1.2 ──┐               shared 5 Mbps up             netem, 20 ms each way
                     ├── router ─────────────────────── delay ─────────────────────── server
roommate 10.77.2.2 ──┘               shared 20 Mbps down
```

- **Topology:** five Linux network namespaces joined by veth pairs. Both users go through the same upload bottleneck (on the router's WAN side) and the same download bottleneck (on the far side, because Linux shapes traffic as it leaves an interface). The 40 ms round trip is added by netem on a separate link, so delay and queueing don't interfere. Offloads (GSO/GRO/TSO) are off so FIFO and CAKE see the same packets.
- **Policies:** FIFO is HTB with a plain FIFO queue (about 300 ms of buffer). SQM is CAKE in best-effort mode with per-host fairness. Meeting priority is CAKE diffserv4 with the meeting device classified into the Voice tin. Classification uses the device's source address and ingress interface, not the packet's DSCP mark, so a self-test checks that a roommate forging the Voice DSCP gets no priority. All three get the same bandwidth.
- **Traffic:** the meeting is a 600 Kbps UDP stream in each direction (a stand-in for call media) plus a timestamped ping; the roommate runs four TCP flows per direction with iperf3.
- **Measurement:** latency from the meeting's ping; loss, jitter, and throughput from iperf3's receiver-side reports; kernel qdisc and classifier counters before and after each run. 3-second warm-up, 15-second measurement, run order shuffled with a fixed seed, all raw files kept. An independent audit recomputes the summaries from the raw files.
- **Timed meeting mode:** `lab/session.py` applies priority for a set time, reads the kernel config back to confirm it, and a separate supervisor restores fair queuing when it expires, including after a restart.

The repository also has a browser dashboard and a Node.js queueing model for exploring the same question on Windows without a Linux kernel. The model is a simplified simulation, not CAKE; its numbers and the kernel lab's are not interchangeable.

## Run it

Kernel lab (an isolated Linux VM with root; Python standard library only):

```sh
sudo python3 lab/netlab.py check                 # verifies netns, HTB, CAKE, netem, flower support
sudo python3 lab/netlab.py setup
sudo python3 lab/netlab.py selftest --duration 8 --output results/linux/selftest
sudo python3 lab/netlab.py batch --duration 15 --repeats 3 --output results/linux/batch
sudo python3 lab/netlab.py teardown
```

Dashboard and model (Node.js 22+, no dependencies):

```sh
node src/server.mjs                # http://127.0.0.1:3210, English / 繁體中文
node --test tests/*.test.mjs       # 29 tests
python3 -m unittest discover -s lab -p "test_*.py"   # 18 lab tests
```

Details: [Linux lab guide](docs/linux-lab.md), [model definition](docs/simulator.md), [portable VM on Windows](docs/portable-vm.md).

## Limits

- QEMU TCG timing (above): the kernel results need a rerun on a native kernel before the smaller differences mean anything.
- Three 15-second runs per cell: enough to see the bufferbloat effect, not enough for statistical significance.
- UDP at a fixed rate stands in for a call; there are no real codecs, adaptive bitrate, or Zoom/Teams quality scores.
- Everything runs in an isolated lab. Wi-Fi, a real home router, and ISP behavior are not tested.
