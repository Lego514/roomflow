# Home incident: recurring latency plateaus and missing IPv6 outcomes

[繁體中文](home-incident.zh-TW.md) · [De-identified evidence](evidence/home-incident.json)

**Status: observations verified; root cause and household repair unconfirmed.** This case describes saved probe behavior, not a verified Zoom/Teams incident. A low gateway median, a slow downstream target, or a lab result alone does not diagnose bufferbloat, identify a device, or prove an ISP fault.

## Evidence window and provenance

The fixed window is **2026-10-07 18:47:19 UTC through 2026-10-12 06:05:02 UTC**, inclusive: **October 7, 14:47:19 through October 12, 02:05:02 EDT**, America/New_York (UTC−04:00), **107.30 elapsed hours**. This supersedes the earlier approximately 34-hour README snapshot; it is not a claim of uninterrupted coverage.

The source is the ignored local SQLite history, `data/home.sqlite`. Previously executed `homenet check`, `path`/`ipv6`, `capacity`, and `bloat` commands generated the records. This analysis used a read-only SQLite URI, `query_only`, and one read transaction; **no network measurement or load test was run to create this case**. The export contains summary statistics and a de-identified timeline, not original individual-packet samples. Raw history and the local log remain unpublished.

| Recorded evidence | Sample size |
|---|---:|
| Checks / per-target latency summary rows | 1,238 / 8,666 |
| Gateway ICMP attempts / external TCP-connect attempts | 6,195 / 12,390 |
| Name-resolution attempts / named-service TCP-connect attempts | 7,428 / 7,428 |
| IPv4/IPv6 comparison batches / target records | 55 / 275 |
| Traces / stored hop-summary rows | 56 / 539 |
| Capacity runs | 80 |
| Historical idle/download/upload load-test runs / phase rows | 14 / 42 |

Check spacing has a 300-second median; one gap exceeds 15 minutes, with a maximum gap of 6,347 seconds. Gaps, potentially skipped checks or host sleep, sequential probes, and collection timing limit coverage; the gap's cause is not established. Stored timestamps identify completed collection batches; they do not establish simultaneous observations across protocols.

## How the snapshot is generated

From the repository root:

```sh
python -B scripts/export-home-incident.py --through 2026-10-12T06:05:02Z --output docs/evidence/home-incident.json
```

The [exporter](../scripts/export-home-incident.py) reads existing rows through the inclusive cutoff and records its source SHA-256. It uses explicit EDT conversion for this October 2026 window, independently of the host timezone. It omits SSIDs, MAC/BSSID, user/roommate identifiers, addresses, endpoint names, raw exception text, and secrets. Public targets receive opaque aliases without an exported mapping. No schema migration or source-database write is performed.

Each timeline value is the **mean of the available per-target TCP-connect p50 values** for the two external targets, not a pooled packet median. Missing values remain `null`; target availability counts are retained. The baseline is the sorted value at zero-based `floor(n × 0.1)`, **21.95 ms** here. A sample is slow above baseline + 50 ms, approximately **71.95 ms**. A retained episode needs two slow checks; two subsequent non-slow checks confirm recovery, while a gap over 15 minutes closes an episode as open-ended. End times denote the last slow observation, not an exact physical recovery time. This is a reporting rule, not a root-cause detector.

## Observed timeline

![Gateway ICMP and external TCP latency from the fixed snapshot; shaded episodes do not establish the cause](home-latency-light.svg)

All times below are EDT (UTC−04:00). “Internet” is the mean-of-target-medians statistic above; episode columns take its median over slow checks.

| Episode | First / last slow observation | Span | Slow checks | Internet median | Gateway median |
|---|---|---:|---:|---:|---:|
| 1 | Oct 7 16:50:12 → 22:05:07 | 5 h 14 m 55 s | 62 | 207.63 ms | 4 ms |
| 2 | Oct 8 00:35:06 → 09:55:06 | 9 h 20 m | 111 | 195.93 ms | 2 ms |
| 3 | Oct 8 14:30:06 → 17:50:06 | 3 h 20 m | 41 | 207.18 ms | 3 ms |

All three episodes have subsequent recovery observations; none ends solely because recording stopped. Their summed first-to-last spans are **17 h 54 m 55 s**, about **17 h 55 m**, with **214 slow checks**. Across the entire window, 243 samples exceed the threshold, so there are also samples not retained in these three episodes. There is no later retained episode under this rule through the cutoff; this does not mean the remaining hours were fault-free.

Gateway medians were low within those periods. However, across the full window, **284/1,238 gateway p95 values exceed 30 ms**, two gateway series contain loss, and the maximum per-check gateway p50 is **306 ms**. Consequently, “the home network is fine throughout” and “Wi-Fi is ruled out” are unsupported.

## Comparisons and the corrected IPv6 denominator

| Comparison | Inside detected episodes | Outside detected episodes | Interpretation |
|---|---:|---:|---|
| IPv6 batches with any missing usable IPv6 outcome while IPv4 answered | **9/9** | **0/46** | An observed association for selected targets, not network-wide IPv6 availability. |
| Explicit unsuccessful IPv6-connect target rows | 18 | 0 | The legacy collector recorded connection attempts without a successful p50. |
| Legacy `no IPv6 address` target rows | 27 | 0 | No usable IPv6 address/result was obtained; absent AAAA data and lookup failures were not distinguished. |
| Capacity runs | 0 | 80 | No matching inside/outside capacity comparison is available. |
| Trace largest-increment heuristic labelled access-side | 9/9 | 46/47 | A candidate region for investigation, not a physical queue-location diagnosis. |

**“9/9” counts batches with at least one qualifying target outcome.** It does not mean nine packets were lost or nine whole-network outages were proved. Those nine batches contain 45 target records: 18 explicit unsuccessful connection outcomes and 27 legacy no-address outcomes. The latter must not be relabelled confirmed DNS failures or IPv6 transport failures. All 230 outside target records have paired responses in this snapshot; missing periods are kept separate rather than making surviving IPv6 samples appear faster. Application address racing/fallback and actual media traffic were not recorded.

All 80 capacity runs are outside the episodes: 77 contain a numeric download estimate (median **276.45 Mbps**) and 80 contain a numeric upload estimate (median **40.54 Mbps**). Three download measurements failed and remain missing, including two HTTP 429 classifications. A failed probe is not zero available bandwidth. Download is client-read payload bytes per elapsed phase; upload is a **client-side payload generation/send estimate**, without remote receiver-confirmed goodput. Neither is provisioned line capacity or directly comparable to the lab's iperf receiver throughput.

The saved trace heuristic labels the largest increment access-side in **55/56** traces, with one labelled home-router-side. Inside episode traces have a 197 ms median terminal effective latency, versus 17 ms outside. ICMP control-plane replies, silent hops, routes, and the heuristic's backward minimum limit attribution; this is not proof that a specific ISP queue is full.

Fourteen historical active tests contain transfers in both directions. The median stored increase—**loaded external TCP p95 minus preceding idle TCP p50**—is **112.24 ms for download** and **67.59 ms for upload**. Download-phase gateway p50 medians are **24.5 ms**, with a median per-phase gateway p95 of **112.5 ms**. This supports investigating load-associated delay, including possible local effects. These short active phases do not establish the cause of the spontaneous multi-hour plateaus; their “idle” phase also does not prove other household traffic was absent.

## Hypotheses and required evidence

| Hypothesis | Supporting observations | Missing evidence / status |
|---|---|---|
| Shared-link queuing / bufferbloat | Sustained external plateaus; historical latency increases under intentional transfers. | No passive utilization or matching capacity samples during episodes; no router-queue counters or home CAKE comparison. **Unconfirmed.** |
| Access-path / ISP congestion or routing effects | External latency rises; trace heuristics point to an access-side increment. | No ISP telemetry; probe attribution cannot distinguish equipment or policy. **Unconfirmed.** |
| Wi-Fi, router, or measurement-host effects | Gateway tails/loss and increased gateway latency in historical download phases. | No wired control, airtime/retry data, or matched host-load evidence. Low episode medians do not exclude these. **Unconfirmed.** |
| IPv6 transport/routing or address-resolution behavior | Missing IPv6 outcomes coincide with sampled episodes while IPv4 responses exist. | Legacy no-address rows lack DNS response/error detail; no packet trace or application fallback data. **Unconfirmed.** |
| A specific device's backup/upload/download | Such traffic could produce load-associated delay. | No device utilization or intervention evidence. **No device or person is implicated.** |

## Actions completed versus pending

**Completed:** the existing collection and historical active tests were saved; this fixed-window analysis recomputed counts, separated observations from hypotheses, clarified legacy IPv6 outcomes, preserved failed measurements, and produced a de-identified reproducible snapshot.

**Not completed:** no household router policy, physical placement, DNS configuration, IPv6 setting, or CAKE deployment is documented as changed for this incident. No controlled device stop/start, wired comparison, ISP fault confirmation, or before/after call-quality validation is present. The later return to lower sampled latency is an observation, **not evidence that this project repaired the network**. Parameterized Linux CAKE experiments provide mechanism evidence only; calibration from a home plateau is not independent home verification.

## Verification plan — not executed here

1. During a future recurrence, first record passive WAN utilization, client/router load and interface counters where access permits; align clocks with the check timestamps. Confirm whether a direction is busy instead of inferring it from latency alone.
2. Compare wired and Wi-Fi observations using the same destination/protocol where practical, retaining gateway tails and host-load data.
3. Record IPv6 address-resolution outcome separately from TCP success/no-success and no-probe cases, across multiple fixed and named targets. Preserve ambiguity for historical rows; do not backfill an assumed DNS cause.
4. If household equipment access and a suitable testing window are available, test one intervention at a time, record actual utilization/throughput and comparable latency windows, then repeat and restore settings. A load test or home CAKE change is future work, not an action taken during this analysis.
5. Validate actual calls separately, with application/media quality evidence and background throughput. A credible improvement needs repeated before/after observations, not just one recovered sample.

The defensible result is a reproducible incident record and a narrower investigation plan. The saved data do not confirm bufferbloat, an offending roommate/device, a DNS fault, an ISP fault, or a successful household repair.
