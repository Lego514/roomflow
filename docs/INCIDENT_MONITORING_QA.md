# Incident monitoring verification — 2026-10-20

Implementation is local and uncommitted. Existing work was preserved. No resume, job application, external notification, or household router setting was changed.

## Delivered behavior

- Three consecutive abnormal checks confirm one incident; two complete healthy checks confirm recovery. Unknown or stale data never counts as recovery.
- SQLite transactions retain samples, incident state and stable opening/recovery IDs. Replaying or retrying checks does not duplicate local transition records. `check` and `watch` atomically export the current aggregate snapshot.
- The homepage shows dated gateway/external/DNS observations, unsuccessful-probe ratios, a chart, and incident details with observations, uncertainty and next checks. English/Traditional Chinese switching preserves the selected event.
- Historical home data, local data and isolated drill results have separate sources. Missing/invalid local evidence never silently falls back to demo data. The API recomputes freshness; a historical snapshot stays historical.
- Unknown intervals and long gaps break incident shading. Unknown layer metrics do not contribute chart points, lines or scale. A clearly labelled logarithmic scale keeps extreme observed values without flattening the normal range; linear scale is available.
- The generated [portable demonstration](../artifacts/demo/RoomFlow.html) embeds the fixed home export plus all three final drill payloads, assets and script. Its [manifest](../artifacts/demo/manifest.json) records input/output hashes.

## Executed checks

| Check | Result |
| --- | ---: |
| Node model/session/API/i18n/monitor-renderer/portable-file tests | 34 passed |
| Python home collection/incident persistence/dashboard tests | 100 passed |
| Python packet lab/incident-drill interpretation tests | 26 passed |
| Total automatic tests | **160 passed, 0 skipped** |
| Real isolated delay / total loss / DNS no-response scenarios | **3 passed** |
| Real SIGTERM failure cleanup and stale dashboard invalidation | Passed |
| Existing source-file hash comparison | 59 checked; only planned files changed |
| Original SQLite raw history comparison | All six original tables retained every prior row |
| `git diff --check` | Passed; pre-existing CRLF normalization warnings only |

Commands and complete outputs are in [`artifacts/tests/incident-monitoring/`](../artifacts/tests/incident-monitoring/). [Machine-readable validation](../artifacts/tests/incident-monitoring/validation.json) and [history preservation](../artifacts/tests/incident-monitoring/history-preservation.json) retain the final results. Local existing history was backed up consistently before incident-table initialization; the backup stays ignored under `tmp/incident-baseline/`.

## Real packet evidence

The final runs used Ubuntu 24.04 under WSL2, kernel `6.18.54.1-microsoft-standard-WSL2`, and isolated client/router/server namespaces. No host route, DNS, firewall, forwarding setting or home router was changed. All owned namespaces were absent after execution, independently rechecked with `ip netns list`.

- **Delay:** configured 350 ms on external egress; measured external TCP p95 approximately 353–358 ms while gateway probes stayed healthy.
- **Loss:** configured deterministic 100% external packet loss; external TCP, HTTP and DNS attempts failed while gateway probes stayed healthy.
- **DNS silence:** actual queries reached a live synthetic responder. Fourteen queries were received: six were deliberately unanswered during the fault and eight replied during baseline/recovery. Direct-IP TCP/HTTP and gateway observations remained healthy.
- Each seven-check run produced exactly **one resolved incident and two local transition records**. Prefix assertions verified no premature opening or recovery.
- A real SIGTERM during an affected loss run preserved failure evidence, removed any old successful dashboard for that output, and cleaned up its namespaces.

See [raw evidence and dashboard payloads](../results/incident-drills/), [interruption evidence](../results/incident-drills-interrupted/loss-evidence.json), and the [repeatable drill instructions](incident-drills.md). A new CI workflow runs these checks on Ubuntu after push; **remote CI has not been executed or claimed as passing**.

## Historical and local observations

The public demonstration is a read-only, de-identified aggregate export of **1,238 completed checks** through `2026-10-12T06:05:02Z`, replaying **26 incidents / 52 local transitions**. Replayed transition records are not claims that notifications were actually sent in the past. These operational rules differ from the earlier case study's three relative-baseline latency episodes.

The local exporter was also run against the existing database after backup. It created incident records and an aggregate view without starting probes. The browser subsequently showed **3,333 local checks**, latest `2026-10-20T05:25:03Z`, including a newly saved check after the initial export. Only the latest 2,000 chart points are sent, with the truncation disclosed; events replay all saved history.

Browser checks covered source switching, DNS drill recovery timestamps with seconds, incident selection, both languages, and no horizontal overflow at a 502 px viewport. Screenshots are in the validation directory. The in-app browser rejects `file://` navigation, so direct opening of the generated portable HTML was not visually tested there. The artifact's embedded scripts/data/hash provenance and absence of external assets were checked automatically; the same renderer was visually checked in the local HTTP application.

## Practical limits

These are sampled probe observations and synthetic fault exercises. They do not confirm the household incident's root cause, a production network rollout, an ISP fault, or improved Zoom/Teams media quality. Failed probe ratios are not call-media packet loss. The collector retains its existing logged-in-user scheduling limits; no new always-on service or external alert delivery was installed.
