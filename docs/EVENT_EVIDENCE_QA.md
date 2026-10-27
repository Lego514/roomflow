# Event evidence, focused charts and recorded replay — 2026-10-20

This update adds numerical incident evidence, selected-event chart focus and step-by-step playback of saved packet drills. It does not change incident thresholds, normalized samples, transition IDs, household network settings, or external alert delivery.

## Measured incident evidence

- All four layers show peak observed check p95/time, configured thresholds, known failed/attempted probes, weighted failure ratio and healthy/abnormal/unknown check counts.
- The summary window is first abnormal through last abnormal, excluding the healthy recovery-confirmation tail. Missing counts remain explicit; unavailable latency is not filled with zero.
- Failure thresholds apply to individual targets; the displayed ratio is weighted across known attempts. A review found and fixed a breach-count bug: one target losing 1/10 and another 0/10 yields 5% overall but still triggers the target-level threshold. Regression tests verify three such abnormal checks show three failure breaches, including a partial-count variant.
- The existing 61 local incidents were enriched. All original raw table rows, normalized sample bytes and 122 transition IDs were retained, without duplicate opening/recovery records. See [production enrichment verification](../artifacts/tests/event-evidence/production-enrichment.json).

## Focus and playback

- Selecting an event focuses the chart on its window with before/after context; **Full history** restores the available chart. Truncated/unavailable context is disclosed and unknown/gap shading remains intact.
- Saved drill payloads contain authoritative frames from the same Python incident state machine. The UI begins paused at the first sample; cards, chart, incidents, notifications and evidence use only the reached prefix.
- Each seven-sample drill follows `normal → normal → pending → pending → open → recovering → resolved`. The fifth sample opens the event, the sixth remains open, and the seventh confirms recovery.
- Play/pause, previous/next and restart work with keyboard focus retained. Changing source/scenario cancels playback and resets; language switching preserves the selected step. A completed incident can be stepped backwards into its earlier open state without revealing final recovery.

## Verification

| Executed check | Result |
| --- | ---: |
| Node HTTP/schema/i18n/renderer/portable artifact suite | 41 passed |
| Python home monitoring/evidence/authoritative replay suite | 113 passed |
| Python lab interpretation and saved-evidence rebuilding suite | 28 passed |
| **Total automatic tests** | **182 passed; 0 skipped** |
| Existing source hash audit | 82 files checked; only planned changes |
| `git diff --check` | Passed; existing CRLF notices only |

Complete logs are in [`artifacts/tests/event-evidence/`](../artifacts/tests/event-evidence/). The generated offline file's tests validate its embedded data/scripts, all seven frame states, input evidence hashes and UI asset hashes, so a stale build after UI edits is detected.

Browser checks used the local HTTP homepage and standalone monitoring page: event focus changed the visible window and reset restored it; DNS sample 4 had no incident, sample 5 opened, sample 6 stayed open, sample 7 resolved; stepping back, pause, scenario reset and English/Traditional Chinese switching were exercised. The standalone page fits its 1,265 px viewport; all new monitor elements fit the 502 px homepage viewport. The pre-existing kernel-results table still has its own scrolling behavior, outside this update. Screenshots: [recorded replay](../artifacts/tests/event-evidence/replay.png), [numerical evidence](../artifacts/tests/event-evidence/evidence.png).

## Saved data and delivery

The fixed home demo remains **1,238 checks / 26 incidents / 52 replayed local transitions** through `2026-10-12T06:05:02Z`. All three drill dashboard files were regenerated from the previously executed real-packet evidence using `scripts/rebuild-drill-dashboards.py`. The raw packet files remain unchanged; no new packet drill or household probe was run for this update. The script audits the saved evidence and refuses interrupted or uncleared runs.

The [updated offline demonstration](../artifacts/demo/RoomFlow.html) includes the new evidence table, focus controls and authoritative replay for all three saved drills. The in-app browser permits HTTP(S) and does not support direct `file://` visual inspection; the generated file was checked automatically, and the same renderer was visually verified in the normal HTTP application.

Source changes remain local and uncommitted. Remote CI was not rerun; no GitHub publication, resume edit, application or external message was made.
