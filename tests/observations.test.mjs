import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createApp } from '../src/server.mjs';
import { validateObservations } from '../src/observations.mjs';

const at = '2026-10-20T05:00:00Z';
function fixture(kind = 'historical-demo') {
  const layer = { status: 'ok', p50Ms: 12, p95Ms: 15, attempts: 10, failed: 0, failurePct: 0, flags: [] };
  const sample = { at, status: 'ok', layers: { gateway: layer, internet: layer, dns: layer, service: layer } };
  return { schemaVersion: 1, source: { kind, label: 'Test measurements', notes: [] },
    policy: { openAfter: 3, recoverAfter: 2, maxGapSeconds: 900, staleAfterSeconds: 900 },
    latest: sample, timeline: [sample], incidents: [], notifications: [] };
}

test('observation API keeps history separate, detects local staleness at request time, and never substitutes demo for local', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'roomflow-observations-'));
  let now = Date.parse(at) + 1000;
  const demo = path.join(dir, 'demo.json');
  const local = path.join(dir, 'observations.json');
  const drillDir = path.join(dir, 'drills');
  fs.mkdirSync(drillDir);
  fs.writeFileSync(demo, JSON.stringify(fixture()));
  fs.writeFileSync(path.join(drillDir, 'delay.json'), JSON.stringify(fixture('lab-drill')));
  const app = createApp({ dataDir: dir, observationsDemoFile: demo, drillDir, now: () => now });
  await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
  t.after(async () => { await app.dispose(); fs.rmSync(dir, { recursive: true, force: true }); });
  const base = `http://127.0.0.1:${app.server.address().port}`;
  const get = async query => {
    const response = await fetch(`${base}/api/observations${query}`);
    return { response, body: await response.json() };
  };
  let result = await get('');
  assert.equal(result.response.status, 200);
  assert.equal(result.body.monitor.status, 'historical');
  assert.equal(result.response.headers.get('cache-control'), 'no-store');
  result = await get('?source=local');
  assert.equal(result.body.monitor.status, 'empty');
  assert.equal(result.body.latest, null);
  assert.deepEqual(result.body.incidents, []);
  fs.writeFileSync(local, JSON.stringify(fixture('local-history')));
  result = await get('?source=local');
  assert.equal(result.body.monitor.status, 'current');
  now += 901000;
  result = await get('?source=local');
  assert.equal(result.body.monitor.status, 'stale');
  assert.equal(result.body.latest.at, at, 'old observations remain available but not relabelled as fresh');
  now = Date.parse(at) - 120000;
  result = await get('?source=local');
  assert.equal(result.body.monitor.status, 'stale');
  assert.equal(result.body.monitor.clockSkew, true);
  assert.equal((await get('?source=drill&scenario=delay')).body.monitor.status, 'historical');
  assert.equal((await get('?source=drill&scenario=loss')).response.status, 503);
  for (const query of ['?source=database', '?source=../../data/home.sqlite', '?source=drill&scenario=../../home']) {
    assert.equal((await get(query)).response.status, 400);
  }
  for (const corrupt of ['null', '{bad', JSON.stringify(fixture('historical-demo')),
    JSON.stringify({ ...fixture('local-history'), latest: { at: 'bad date' } })]) {
    fs.writeFileSync(local, corrupt);
    result = await get('?source=local');
    assert.equal(result.response.status, 503);
    assert.equal(result.body.latest, undefined);
    assert.equal((await fetch(`${base}/api/status`)).status, 200);
  }
  fs.writeFileSync(local, JSON.stringify(fixture('local-history')));
  assert.equal((await get('?source=local')).response.status, 200);
  assert.equal((await fetch(`${base}/api/observations`, { method: 'POST' })).status, 405);
});

test('observation API rejects impossible metrics and malformed incidents', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'roomflow-observations-bad-'));
  const demo = path.join(dir, 'demo.json');
  const app = createApp({ dataDir: dir, observationsDemoFile: demo });
  await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
  t.after(async () => { await app.dispose(); fs.rmSync(dir, { recursive: true, force: true }); });
  const base = `http://127.0.0.1:${app.server.address().port}/api/observations`;
  const invalid = [];
  let value = fixture(); value.timeline[0].layers.gateway.failurePct = 101; invalid.push(value);
  value = fixture(); value.timeline[0].layers.gateway.failed = 11; invalid.push(value);
  value = fixture(); value.timeline[0].layers.gateway.p50Ms = -1; invalid.push(value);
  value = fixture(); value.incidents = [{ id: 'incomplete', status: 'resolved' }]; invalid.push(value);
  for (const damaged of invalid) {
    fs.writeFileSync(demo, JSON.stringify(damaged));
    assert.equal((await fetch(base)).status, 503);
  }
});

function replayFixture() {
  const payload = fixture('lab-drill');
  const times = [0, 5, 10].map(seconds => new Date(Date.parse(at) + seconds * 1000).toISOString());
  payload.timeline = times.map(time => ({ ...structuredClone(payload.latest), at: time }));
  payload.latest = payload.timeline[2];
  const evidenceLayers = {};
  for (const name of ['gateway', 'internet', 'dns', 'service']) evidenceLayers[name] = {
    peakP95Ms: 15, peakP95At: times[0], latencyThresholdMs: 120, failureThresholdPct: 5,
    attempts: 30, failed: 0, failurePct: 0, countsComplete: true, countedChecks: 3,
    missingCountChecks: 0, abnormalChecks: 0, healthyChecks: 3, unknownChecks: 0, latencyBreaches: 0, failureBreaches: 0,
  };
  evidenceLayers.internet = { ...evidenceLayers.internet, peakP95Ms: 200, peakP95At: times[2],
    abnormalChecks: 3, healthyChecks: 0, latencyBreaches: 3 };
  const incident = { id: 'incident-test', status: 'open', startedAt: times[0], openedAt: times[2],
    lastObservedAt: times[2], lastAbnormalAt: times[2], resolvedAt: null, affectedLayers: ['internet'],
    observations: [], unknowns: [], nextChecks: [],
    evidence: { startAt: times[0], endAt: times[2], checkCount: 3, layers: evidenceLayers } };
  const transition = { id: 'incident-test:opened', incidentId: incident.id, at: times[2], type: 'opened' };
  payload.incidents = [incident]; payload.notifications = [transition];
  payload.replay = { available: true, totalSamples: 3,
    frames: times.map((time, index) => ({ sampleCount: index + 1, at: time, stage: index < 2 ? 'pending' : 'open',
      incidents: index === 2 ? [structuredClone(incident)] : [], notifications: index === 2 ? [structuredClone(transition)] : [],
      pendingAbnormalChecks: index < 2 ? index + 1 : 0, pendingRecoveryChecks: 0 })) };
  return payload;
}

test('numerical evidence and replay frame validation rejects future outcomes and impossible totals', () => {
  assert.doesNotThrow(() => validateObservations(replayFixture(), 'lab-drill'));
  const future = new Date(Date.parse(at) + 60000).toISOString();
  const mutations = [
    payload => { payload.replay.frames[0].incidents = structuredClone(payload.incidents); },
    payload => { payload.replay.frames[0].notifications = structuredClone(payload.notifications); },
    payload => { payload.incidents[0].evidence.layers.internet.peakP95At = future; },
    payload => { payload.incidents[0].evidence.layers.internet.failed = 31; },
    payload => { payload.incidents[0].evidence.layers.internet.countedChecks = 4; },
    payload => { payload.replay.frames[1].sampleCount = 3; },
    payload => { payload.replay.frames.pop(); },
  ];
  for (const mutate of mutations) {
    const payload = replayFixture(); mutate(payload);
    assert.throws(() => validateObservations(payload, 'lab-drill'));
  }
  const older = fixture('lab-drill');
  assert.doesNotThrow(() => validateObservations(older, 'lab-drill'), 'old evidence without optional additions stays readable');
});
