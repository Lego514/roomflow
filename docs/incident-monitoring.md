# Observation incidents / 量測事件

RoomFlow connects saved network observations to an incident lifecycle and a small monitoring view. Incidents describe probe behavior; they do not establish an ISP fault, a physical queue location, or actual call quality.

## Try the demonstration

```sh
npm start
# Open http://127.0.0.1:3210
```

The first panel is the measurement view. Its default source is **de-identified historical measurements**, with collection dates shown explicitly. The existing meeting-mode simulator remains below it and has its own scope.

The portable demonstration is [`artifacts/demo/RoomFlow.html`](../artifacts/demo/RoomFlow.html). Open the file directly in a browser; it contains its own data, styles, and script and needs no server or Internet connection. Rebuild it with:

```sh
node scripts/build-observation-demo.mjs
```

The historical source is a fixed aggregate export of the existing home history. It preserves unsuccessful attempts and missing values, and contains no network names, hardware addresses, individual targets, or raw error text. Its new operational incidents use the rules below; their count need not equal the earlier case study's three external-latency episodes, which used a different, two-sample relative-baseline rule.

## Event rules

- **Open:** three consecutive checks with a measured abnormality. The event starts at the first abnormal check and is confirmed on the third. A single spike does not open an event.
- **Continue:** subsequent abnormal checks update the existing event, including affected layers. They do not create another opening notification.
- **Resolve:** two consecutive checks in which all required layers have complete healthy observations. The first healthy check alone is not recovery confirmation.
- **Unknown:** no attempted probes, missing metrics, or missing required layers cannot count as healthy recovery. Failed attempts and absent attempts are different observations.
- **Gap:** a gap longer than 15 minutes breaks a pending opening or recovery streak. An already open incident stays open, with a recorded evidence gap, until there is measured recovery. Sleep or a stopped collector is not a network repair.
- **Duration:** `durationSeconds` sums the intervals between adjacent classified observations, excluding long gaps and intervals touching an unknown check. `spanSeconds` separately retains the first-observation-to-confirmed-recovery wall span (or first-to-latest span for an open event). Neither proves continuous downtime between samples. No timer silently resolves an event.

Each incident retains observation and confirmation times, affected layers, observations, unknowns, next checks, and transition IDs. Local opening/recovery records are deduplicated across repeated exports and process restarts. These are **local notification records**; this feature does not send email, chat messages, or webhooks.

## Inspect measured event evidence

Incident details show all four probe layers, including healthy comparisons. Each layer records the highest observed per-check p95 and its timestamp, the configured latency/failure thresholds, unsuccessful attempts over known attempts, and healthy/abnormal/unknown check counts.

The numerical evidence window starts at the first abnormal check and ends at the last abnormal check. Recovery-confirmation checks are excluded from these totals so later healthy samples do not dilute the event's failure ratio. Healthy or unknown checks *between* abnormal checks remain included. Partial count coverage is labelled; absent latency stays missing instead of becoming zero. The maximum of check p95 summaries is not a pooled event p95.

Failure thresholds are evaluated per target, while the displayed ratio is weighted across known attempts. A single target can therefore breach even when the combined ratio equals or falls below the threshold. Breach counts use the recorded target-level observation flag, including partial-count cases.

Clicking an event focuses the chart around its observations and recovery, with a small before/after context. The selected time window is displayed; **Full history** restores the available timeline. If chart history was truncated or the event lies outside retained points, the view discloses missing context rather than manufacturing it.

## Replay a saved fault drill

Select **Isolated fault drill**, then delay, loss or DNS silence. The view begins at the first saved sample. Use **Play/Pause**, **Previous/Next** and **Restart** to inspect the sequence. Two baseline checks are followed by three abnormal checks and two recovery checks:

```text
normal → normal → pending → pending → open → recovering → resolved
```

Each step's incident state, transition records and numerical evidence come from the same Python state machine replayed on that prefix of saved observations. Cards, chart points, incident details and maxima show only samples reached so far. The first recovery check leaves the event open; the second resolves it. Source/scenario changes stop playback. Language changes preserve the selected step.

This is recorded-data playback, not a new packet drill or a live network repair. Up to 200 samples are precomputed for a lab replay; larger archives keep their saved view without generating unbounded replay data. Demo and local history remain ordinary observation views.

To update presentation files from the original saved packet evidence without sending any new probes:

```sh
python scripts/rebuild-drill-dashboards.py
node scripts/build-observation-demo.mjs
```

The rebuild audits each successful raw packet run, preserves its bytes and records its hash. It refuses interrupted or uncleared evidence. To collect a new real packet experiment, use the separate Linux drill command in the [drill guide](incident-drills.md).

## Use local measurements

The existing collector records `check` runs in the local SQLite history. Successful collection also updates the incident view and atomically writes `data/observations.json`; a later collection/export rebuilds the view from saved checks, so a failed export does not discard measurements.

```sh
python -m homenet dashboard
python -m homenet incidents
```

Select **Local measurements** in the homepage to inspect the export. This reads aggregate JSON; loading the page does not start probes or traffic loads. Missing local export, stale collection, invalid files, and a healthy latest probe are distinct UI conditions. A historical snapshot never changes into a live healthy indicator simply because the page was refreshed.

The Windows schedule still runs only while the user is logged on. This is not a 24/7 monitoring service, and adding this view does not install or change scheduled tasks.

## Read-only HTTP API

| Request | Evidence |
|---|---|
| `/api/observations?source=demo` | Fixed historical aggregate export |
| `/api/observations?source=local` | Local `data/observations.json`, or an explicit empty state |
| `/api/observations?source=drill&scenario=delay` | Saved delay drill results |
| `/api/observations?source=drill&scenario=loss` | Saved loss drill results |
| `/api/observations?source=drill&scenario=dns` | Saved DNS no-response drill results |

The server only serves these allowlisted aggregate files; it does not expose the SQLite database or logs. Invalid/corrupt saved evidence returns an error instead of substituting the demo. Each response recomputes local freshness with the request time; over 15 minutes old is stale. Future timestamps more than a minute ahead also flag stale/clock mismatch. The latest saved observation remains visible with its original date.

## Verify a known failure

See [isolated Linux drills](incident-drills.md). The delay, packet-loss, and DNS no-response cases use isolated namespaces and actual packet observations. Injected truth, measured evidence, event opening, and recovery are saved separately. A unit-test fixture or an in-browser model is not labelled as an executed packet drill.

## 中文使用摘要

1. 執行 `npm start`，首頁先看固定的去識別化歷史展示；也可直接開啟離線 HTML。
2. 本機量測由既有 `homenet check` 收集。`dashboard` 從既有資料重建事件並匯出，不會主動測速或改路由器。
3. 連續三筆異常開案、連續兩筆完整正常才結案；單次尖峰、沒有資料、休眠及停止收集不當成修復。
4. 每個事件可查量測依據、尚未確認的部分、下一步排查與本機開案／恢復紀錄。
5. 歷史案例、隔離演練與本機資料分開標示；探測失敗比例不等於視訊媒體丟包率。
