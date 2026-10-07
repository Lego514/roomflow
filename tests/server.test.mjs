import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createApp } from '../src/server.mjs';
import { validateExperiment, summarizeRuns } from '../src/experiment.mjs';

test('HTTP experiment, export, expiry, and restart recovery work end to end', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'roomflow-server-'));
  const evidenceDir = path.join(dir, 'evidence');
  let time = 50000;
  let app = createApp({ dataDir: dir, evidenceDir, now: () => time });
  const listen = async () => {
    await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
    return `http://127.0.0.1:${app.server.address().port}`;
  };
  let base = await listen();
  t.after(async () => { await app.dispose(); fs.rmSync(dir, { recursive: true, force: true }); });
  const post = (url, value, origin) => fetch(`${base}${url}`, { method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(origin ? { Origin: origin } : {}) }, body: JSON.stringify(value) });
  const initial = await (await fetch(`${base}/api/status`)).json();
  assert.equal(initial.preview.config.mode, 'fair');
  assert.ok(Number.isFinite(initial.preview.summary.rttP95Ms));
  const evidenceResponse = await fetch(`${base}/api/kernel-evidence`);
  assert.equal(evidenceResponse.status, 200);
  const evidence = await evidenceResponse.json();
  assert.equal(evidence.engine, 'linux-kernel');
  assert.ok(['pending', 'verified'].includes(evidence.status));
  if (evidence.status === 'pending') assert.match(evidence.message, /尚在執行/);
  assert.equal((await fetch(`${base}/api/kernel-evidence/not-a-file`)).status, 404);
  assert.equal(initial.capability.kernelAvailable, false);
  assert.equal((await post('/api/session', { action: 'start', durationSeconds: 10, device: 'meeting' }, 'https://example.com')).status, 403);
  assert.equal((await post('/api/session', { action: 'start', durationSeconds: 10, device: 'meeting' })).status, 200);
  const active = await (await fetch(`${base}/api/status`)).json();
  assert.equal(active.session.mode, 'meeting');
  assert.equal(active.preview.config.mode, 'priority');
  assert.equal((await post('/api/session', { action: 'start', durationSeconds: 10, device: 'meeting' })).status, 409);
  assert.equal((await post('/api/experiments', { upMbps: -1 })).status, 400);
  const response = await post('/api/experiments', { scenario: 'mixed', durationSeconds: 5, repeats: 1 });
  assert.equal(response.status, 202);
  const { id } = await response.json();
  let job;
  for (let attempt = 0; attempt < 100; attempt++) {
    job = await (await fetch(`${base}/api/experiments/${id}`)).json();
    if (['complete','failed'].includes(job.status)) break;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  assert.equal(job.status, 'complete', job.error);
  assert.equal(job.result.runs.length, 3);
  assert.equal(job.result.summary.length, 3);
  assert.ok(job.result.series.length > 0);
  assert.ok(job.result.summary.every(row => Number.isFinite(row.meetingRttP95Ms)));
  const csv = await (await fetch(`${base}/api/experiments/${id}/export.csv`)).text();
  assert.equal(csv.trim().split('\n').length, 4);
  assert.match(csv, /discrete-event-model/);
  time += 11000;
  await app.dispose();
  app = createApp({ dataDir: dir, evidenceDir, now: () => time }); base = await listen();
  const restored = await (await fetch(`${base}/api/status`)).json();
  assert.equal(restored.session.mode, 'normal');
  assert.equal(restored.preview.config.mode, 'fair');
  assert.equal(restored.preview.summary.rttP95Ms, initial.preview.summary.rttP95Ms);
  assert.equal((await (await fetch(`${base}/api/experiments/${id}`)).json()).status, 'complete');
  assert.equal((await fetch(`${base}/api/experiments/no-such-id`)).status, 404);
});

test('bounded experiment inputs reject invalid and expensive requests', () => {
  for (const values of [{ repeats: 100 }, { durationSeconds: 9999 }, { scenario: 'random' }, { seed: -1 }, { upMbps: '5' }, { downMbps: NaN }, null, []]) {
    assert.throws(() => validateExperiment(values));
  }
  assert.deepEqual(validateExperiment({}), { scenario:'mixed',durationSeconds:60,repeats:3,seed:42,upMbps:5,downMbps:20,baseRttMs:40 });
});

test('missing or corrupted saved results become failed jobs instead of false completion', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'roomflow-lost-result-'));
  const experiments = path.join(dir, 'experiments');
  fs.mkdirSync(experiments);
  const ids = ['11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222', '33333333-3333-4333-8333-333333333333'];
  for (const id of ids) fs.writeFileSync(path.join(experiments, `${id}.meta.json`), JSON.stringify({ id, status:'complete', progress:1, createdAt:1 }));
  fs.writeFileSync(path.join(experiments, `${ids[1]}.json`), '{broken json');
  fs.writeFileSync(path.join(experiments, `${ids[2]}.json`), 'null');
  const app = createApp({ dataDir:dir });
  t.after(async () => { await app.dispose(); fs.rmSync(dir, { recursive:true, force:true }); });
  await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${app.server.address().port}`;
  for (const id of ids) {
    const response = await fetch(`${base}/api/experiments/${id}`);
    assert.equal(response.status, 200);
    const job = await response.json();
    assert.equal(job.status, 'failed');
    assert.match(job.error, /saved experiment result/i);
    assert.equal(job.result, undefined);
    assert.equal((await fetch(`${base}/api/experiments/${id}/export.json`)).status, 409);
    assert.equal(JSON.parse(fs.readFileSync(path.join(experiments, `${id}.meta.json`), 'utf8')).status, 'failed');
  }
});

test('worker termination handles metadata write failure without an uncaught callback', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'roomflow-worker-write-'));
  let app = createApp({ dataDir:dir });
  t.after(async () => { await app.dispose(); fs.rmSync(dir, { recursive:true, force:true }); });
  await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
  let base = `http://127.0.0.1:${app.server.address().port}`;
  const response = await fetch(`${base}/api/experiments`, { method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ durationSeconds:180, repeats:5 }) });
  assert.equal(response.status, 202);
  const { id } = await response.json();
  const blocker = path.join(dir, 'experiments', `${id}.meta.json.tmp`);
  fs.mkdirSync(blocker);
  await app.dispose();
  fs.rmdirSync(blocker);
  app = createApp({ dataDir:dir });
  await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${app.server.address().port}`;
  const job = await (await fetch(`${base}/api/experiments/${id}`)).json();
  assert.equal(job.status, 'failed');
  assert.match(job.error, /restart|without a result/);
});

test('aggregation preserves missing RTT and missing policies instead of zero success', () => {
  const runs = [{ policy:'fifo', summary:{ rttP95Ms:null, meetingJitterMs:1, meetingLossPct:2, meetingReceivedMbps:2, roommateThroughputMbps:3 } }];
  const rows = summarizeRuns(runs, 'mixed');
  assert.equal(rows[0].meetingRttP95Ms, null);
  assert.equal(rows[0].meetingMbps, 2);
  assert.equal(rows[1].repeats, 0);
  assert.equal(rows[1].meetingRttP95Ms, null);
  assert.equal(rows[1].backgroundMbps, null);
});

test('saved kernel evidence handles pending, exact JSON and CSV exports, malformed files, and recovery', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'roomflow-kernel-evidence-'));
  const evidenceDir = path.join(dir, 'evidence');
  const app = createApp({ dataDir:path.join(dir, 'data'), evidenceDir });
  t.after(async () => { await app.dispose(); fs.rmSync(dir, { recursive:true, force:true }); });
  await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${app.server.address().port}`;
  const pending = await fetch(`${base}/api/kernel-evidence`);
  assert.equal(pending.status, 200);
  assert.deepEqual(await pending.json(), { status:'pending', engine:'linux-kernel', message:'Linux 重複實驗尚在執行' });
  assert.equal((await fetch(`${base}/api/kernel-evidence/export.csv`)).status, 404);

  fs.mkdirSync(path.join(evidenceDir, 'batch'), { recursive:true });
  const summaryFile = path.join(evidenceDir, 'summary.json');
  const evidence = { status:'verified', engine:'linux-kernel', environment:{runCount:36},
    summary:[{policy:'sqm', scenario:'both', rttP95MeanMs:48.5, meetingUpJitterMeanMs:null}],
    findings:['Fixture: measured values are retained.'], warnings:[], rawCsvUrl:'/api/kernel-evidence/export.csv' };
  fs.writeFileSync(summaryFile, JSON.stringify(evidence));
  const csv = 'engine,policy,scenario,p95_rtt_ms\nlinux-kernel,sqm,both,48.5\n';
  fs.writeFileSync(path.join(evidenceDir, 'batch', 'measurements.csv'), csv);
  const valid = await fetch(`${base}/api/kernel-evidence`);
  assert.equal(valid.status, 200);
  assert.deepEqual(await valid.json(), evidence);
  assert.equal(valid.headers.get('cache-control'), 'no-store');
  const exported = await fetch(`${base}/api/kernel-evidence/export.csv?file=ignored.json`);
  assert.equal(exported.status, 200);
  assert.match(exported.headers.get('content-type'), /^text\/csv/);
  assert.equal(exported.headers.get('content-disposition'), 'attachment; filename="roomflow-linux-measurements.csv"');
  assert.equal(await exported.text(), csv);
  assert.equal((await fetch(`${base}/api/kernel-evidence/arbitrary.json`)).status, 404);
  assert.equal((await fetch(`${base}/api/kernel-evidence`, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})).status, 405);

  for (const damaged of ['{incomplete', 'null', JSON.stringify({engine:'discrete-event-model', status:'verified', summary:[]})]) {
    fs.writeFileSync(summaryFile, damaged);
    const response = await fetch(`${base}/api/kernel-evidence`);
    assert.equal(response.status, 503);
    const body = await response.json();
    assert.match(body.error, /evidence.*unavailable/i);
    assert.equal(body.status, undefined, 'corrupt evidence must not appear verified or pending');
    assert.equal((await fetch(`${base}/api/status`)).status, 200, 'a malformed evidence file must not crash the server');
  }
  fs.writeFileSync(summaryFile, JSON.stringify(evidence));
  assert.deepEqual(await (await fetch(`${base}/api/kernel-evidence`)).json(), evidence);
});
