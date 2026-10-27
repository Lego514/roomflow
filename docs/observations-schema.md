# Observation snapshot contract (version 1)

`homenet` exports a privacy-filtered JSON snapshot for the RoomFlow home page.
This snapshot describes selected saved probes; it does not diagnose an ISP,
measure real meeting quality, or prove a repair.

```sh
# Saved local history, current/stale evaluated at export time; also persists
# local incidents without running probes.
python -m homenet dashboard --output data/observations.json
python -m homenet incidents

# Reproducible historical demo; source opened with SQLite URI mode=ro,
# query_only and one read transaction. No schema migrations or source writes.
python scripts/export-observations.py --database data/home.sqlite --through 2026-10-12T06:05:02Z --output docs/evidence/observations-demo.json

# Portable fallback if only the previous de-identified two-layer file remains.
# Absent attempts, p95, failure ratios, DNS and service observations stay unknown.
python scripts/export-observations.py --sanitized-history docs/evidence/home-incident.json --through 2026-10-12T06:05:02Z --output data/observations-partial-demo.json
```

Every completed `python -m homenet check` or `watch` check saves raw summaries
and incident transitions in one SQLite transaction, then exports
`data/observations.json`. The export re-reads history under a writer lock and
publishes JSON with a same-directory temporary file plus atomic replacement.
Overlapping scheduled writers cannot publish an older pre-save snapshot after
a newer one. An export failure leaves the saved SQLite check available for the
next export; no partial JSON replaces the previous document.

## Top-level fields

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Integer `1`. |
| `source` | `kind` (`local-history`, `historical-demo`, `lab-drill`), display `label`, full-history `windowStart`/`windowEnd`, `generatedAt`, and explanatory `notes`. |
| `policy` | Open/recovery streak sizes, gap/stale thresholds, required layers, probe thresholds and aggregation/duration semantics. |
| `latest` | Last saved observation, or `null` when empty. It is not a current-health assertion. |
| `timeline` | At most the latest 2,000 samples, in chronological order. |
| `timelineTotal`, `timelineTruncated` | Full sample count and whether the visible timeline is truncated. Incident replay always uses the full history. |
| `incidents` | All incident summaries; open incidents remain open across unknown observations and collection gaps. |
| `notifications` | One durable local `opened` and, if confirmed, one `resolved` transition per incident. No external notifications are sent. For demo exports these are replay results, not messages sent in the past. |
| `monitor` | `status` (`current`, `stale`, `historical`, `empty`), `evaluatedAt`, `lastObservedAt`, `ageSeconds`, and pending streak counters. |
| `replay` | Lab drills only: authoritative prefix `frames`, `totalSamples`, and `available`. Each frame contains only state derived from observations available through that frame. |

Timestamps use UTC with explicit `Z`. Local history becomes `stale` when the
latest check is more than 900 seconds old (or over 60 seconds in the future,
reported as `monitor.clockSkew`). Demo and lab sources use
`historical`, including when their last sample is healthy. Aging never closes an
incident or adds unobserved time to its duration.

The historical exporter pins `monitor.evaluatedAt` to its cutoff and uses the
actual export time for `source.generatedAt`. Re-exporting the same cutoff
reproduces observations and incidents while updating generation metadata.

## Samples and layers

Each sample contains `at`, `status` (`ok`, `degraded`, `unknown`) and `layers`.
The four required layer keys are `gateway`, `internet`, `dns` and `service`.
No target name or address is exported.

| Layer field | Meaning |
| --- | --- |
| `p50Ms` | Mean of available target p50 summaries; not a pooled median. |
| `p95Ms` | Maximum target p95 summary; not a pooled percentile. |
| `attempts`, `failed` | Sum of recorded attempts and unsuccessful probes. Unknown counts are `null`. Stored percentages are converted to counts only when consistent with an integer outcome. |
| `failurePct` | `100 * failed / attempts`; `null` without known positive attempts. TCP/lookup failures are not video packet-loss measurements. |
| `status` | `degraded` for observed threshold excess; `unknown` for incomplete/unavailable observations without a positive anomaly; otherwise `ok`. |
| `flags` | Whitelisted machine labels such as `high-p95`, `unsuccessful-probes`, `no-probes`, `incomplete-targets`, `incomplete-observation`, `conflicting-target-records`, or `missing-metrics`. |
| `complete` | Enough valid observations for that layer to participate in healthy recovery. |
| `observedSeries`, `expectedSeries` | Available/expected target series counts when known. Live expectations are 1 gateway, 2 internet, 2 DNS, 2 service series. |

The project thresholds are unsuccessful probes **greater than 5%**, or target
p95 **greater than 30/120/200/250 ms** for gateway/internet/DNS/service.
When only p50 is retained, p50 above the same bound is sufficient evidence of
slow observations; a low p50 without p95 and counts is insufficient evidence
of health. Attempted probes with no successful outcomes are degraded. Zero
attempts or an absent series are unknown, never a measured outage or recovery.

Sample status is degraded if any layer has a positive anomaly. A partially
missing check can therefore retain an observed anomaly while remaining
ineligible for healthy recovery. Otherwise every required layer must be
complete and healthy for the check to be `ok`; incomplete checks are unknown.
Exact duplicate legacy rows are deduplicated before aggregation. Conflicting
rows for one target and timestamp remain incomplete, with counts unavailable.

## Incident state and duration

Three consecutive degraded checks open one incident, with `startedAt` set to
the first abnormal check and `openedAt` to the third. More degraded checks
update that incident and merge `affectedLayers`; they do not create repeated
open alerts. Two consecutive complete healthy checks resolve it at the second
healthy check. Unknown checks and gaps over 900 seconds reset pending opening
and recovery streaks. They never resolve an open incident. The first check
after a gap can start a new streak.

Each incident contains `id`, `status` (`open`/`resolved`), `startedAt`,
`openedAt`, `lastObservedAt`, `lastAbnormalAt`, optional `resolvedAt`,
`affectedLayers`, `abnormalChecks`, `observations`, `unknowns`, `nextChecks`,
`evidenceGaps`, `evidence` and `transitions`. Transition IDs are stable
`<incident-id>:opened` / `<incident-id>:resolved` and have `type` and `at`.
Notification entries add `incidentId`.

`durationSeconds` is the bounded observed monitoring span, including the
healthy confirmation checks, with collection gaps and intervals adjoining an
unknown check excluded. It is **not proven continuous downtime**.
`spanSeconds` is the wall-clock span from `startedAt` through
`lastObservedAt`/confirmed recovery, including gaps. Neither extends into an
unobserved present. `evidenceGaps` records `from`, `to` and a machine `reason`.

### Numerical incident evidence

`evidence` contains `startAt`, `endAt`, `checkCount` and all four `layers`,
including healthy layers for simultaneous comparison. Its inclusive window is
`startedAt` through `lastAbnormalAt`; later recovery confirmation checks are
excluded from these statistics. Healthy and unknown checks *between* abnormal
checks are included. This window is an observation envelope, not a claim that
every check or every instant was abnormal.

| Evidence layer field | Meaning |
| --- | --- |
| `peakP95Ms`, `peakP95At` | Highest available per-check p95 and first timestamp attaining it. Both are `null` without an observed p95. This is a maximum of summaries, not a pooled event p95. Zero-attempt checks cannot supply latency evidence. |
| `latencyThresholdMs`, `failureThresholdPct` | The exact fixed project thresholds used for this evidence. |
| `attempts`, `failed`, `failurePct` | Sum of checks with valid known integer attempt/failure counts; ratio is `100 * sum(failed) / sum(attempts)`, not a mean of percentages. Counts are `null` if none are known; ratio is `null` with no known positive attempts. |
| `countsComplete`, `countedChecks`, `missingCountChecks` | Whether every check in this window has known counts, and how many do/do not. Partial totals cover only counted checks; missing checks do not become failures or successes. Known zero-attempt checks count as known counts while their observation remains unknown. |
| `abnormalChecks`, `healthyChecks`, `unknownChecks` | Layer classification counts over the evidence window. Their sum equals `checkCount`. |
| `latencyBreaches`, `failureBreaches` | Number of checks with observed latency/failure threshold excess. Latency may use an observed p50 when p95 is absent, while `peakP95Ms` stays `null` if no p95 was retained. Failure breaches use the canonical per-target `unsuccessful-probes` observation, even when complete layer totals are unavailable. |

Failure thresholds apply to **each target**, while layer and event ratios use
weighted attempt totals across targets. `failureBreaches` therefore counts
checks retaining the canonical `unsuccessful-probes` observation: one target
with 1/10 failures and a second with 0/10 gives a weighted layer ratio of 5%,
yet the first target exceeds the 5% threshold. A target's known breach remains
evidence even if another target has missing counts and the layer's weighted
ratio is unavailable.

These structured numbers are separate from `observations`, `unknowns` and
`nextChecks`, so renderers can format bilingual values without interpreting
free-form strings. Replaying saved history enriches old incident payloads with
evidence while preserving immutable samples, incident IDs and transition IDs;
it does not issue another local opening or recovery transition.

### Saved drill replay

Only `lab-drill` snapshots include `replay`. Frames begin at `sampleCount: 1`
and use the same Python incident state machine on each chronological,
deduplicated sample prefix. Each frame has `sampleCount`, `at`, `stage`,
`incidents`, `notifications`, `pendingAbnormalChecks` and
`pendingRecoveryChecks`. Renderers use the original timeline sliced to
`sampleCount` for its observations, while taking event state and numerical
evidence from that frame. Future peaks, event opening, recovery and transition
records therefore cannot appear early.

Stages are `normal` before a pending incident, `pending` during the abnormal
confirmation streak, `open` for an active incident, `recovering` during its
healthy confirmation streak and `resolved` after confirmed recovery. With no
active incident, an unknown latest check has stage `unknown`; an unknown check
during an active incident leaves stage `open` and resets the recovery streak.
Collection gaps use the same streak reset rules as ordinary monitoring.

Prefix frames are generated only for drills of at most 200 distinct samples,
bounding replay work and snapshot size. Larger drills retain their complete
event replay and ordinary bounded timeline, but return
`replay: {"frames": [], "totalSamples": N, "available": false,
"reason": "sample-limit"}`. An empty drill has no frames and
`available: true`. Ordinary local and historical exports have no `replay` key.

SQLite stores aggregate samples, incident payloads and local transition rows.
`BEGIN IMMEDIATE` serializes scheduled writers; transition primary keys and
`UNIQUE(incident_id,type)` prevent duplicate alerts. Saved timestamps are
immutable and chronological: repeating an existing saved check is a no-op;
conflicting or newly appended older observations are rejected rather than
rewriting an already emitted alert. Replay arbitrary historical order in a
fresh database or read-only export. Pure replay sorts samples and deduplicates
identical timestamps before calculating state.

## Python integration

```python
from homenet.dashboard import build_dashboard
from homenet.incidents import sample_from_layers

# layers contains lists of homenet.stats.Series. Isolated lab drills may use
# one target per layer and explicitly set expected_series to 1 for each.
sample = sample_from_layers(at, layers, expected_series={
    "gateway": 1, "internet": 1, "dns": 1, "service": 1,
})
snapshot = build_dashboard(samples, source_kind="lab-drill", label="Delay drill",
                           evaluated_at=samples[-1]["at"],
                           generated_at=samples[-1]["at"], notes=[])
```

The fixed committed demo replays 1,238 pre-existing checks through
`2026-10-12T06:05:02Z`, resulting in 26 incidents and 52 replay transitions
under this incident policy. Those totals differ from the older slow-period
analysis because this policy uses all four layers, tail latency, unsuccessful
probes, three abnormal checks and two complete healthy checks. No new home
measurement or confirmed fix is claimed.
