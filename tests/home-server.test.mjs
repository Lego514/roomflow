import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createApp } from '../src/server.mjs';

test('quick-check HTTP runs only on explicit POST and accepts no targets or commands', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'roomflow-home-http-'));
  let starts = 0, disposed = false;
  const id = '12345678-1234-4234-8234-123456789012';
  let current = null;
  const controller = {
    get(key) { return key && key !== id ? null : current; },
    start() {
      if (current?.status === 'running') {
        const error = new Error('busy'); error.status = 409; error.job = current; throw error;
      }
      starts++;
      return current = { id, status:'running', startedAt:'2026-10-27T05:00:00Z', completedAt:null, errorCode:null, result:null };
    },
    async dispose() { disposed = true; },
  };
  const app = createApp({ dataDir:dir, quickCheckController:controller });
  await new Promise(resolve => app.server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${app.server.address().port}`;
  t.after(async () => { await app.dispose(); fs.rmSync(dir, {recursive:true, force:true}); });
  const post = (body, extraHeaders = {}) => fetch(`${base}/api/quick-check`, {
    method:'POST', headers:{'Content-Type':'application/json', ...extraHeaders}, body:JSON.stringify(body),
  });
  assert.deepEqual(await (await fetch(`${base}/api/quick-check`)).json(), {job:null});
  for (const page of ['/', '/lab.html', '/monitor.html']) assert.equal((await fetch(base + page)).status, 200);
  assert.equal(starts, 0, 'reading pages and status must never generate probe traffic');
  for (const input of [null, [], {target:'example.com'}, {command:'anything'}, {dataDir:'anywhere'}]) {
    assert.equal((await post(input)).status, 400);
  }
  assert.equal((await post({}, {Origin:'https://example.com'})).status, 403);
  assert.equal((await fetch(`${base}/api/quick-check`, {method:'POST', body:'{}'})).status, 415);
  assert.equal(starts, 0);
  let response = await post({});
  assert.equal(response.status, 202);
  assert.equal((await response.json()).job.id, id);
  response = await post({});
  assert.equal(response.status, 409);
  assert.equal((await response.json()).job.id, id);
  assert.equal(starts, 1, 'a second browser click must attach to the existing job');
  assert.equal((await (await fetch(`${base}/api/quick-check/${id}`)).json()).job.status, 'running');
  assert.equal((await fetch(`${base}/api/quick-check/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa`)).status, 404);
  assert.equal((await fetch(`${base}/api/quick-check/not-an-id`)).status, 404);
  const status = await (await fetch(`${base}/api/status`)).json();
  assert.equal(status.capability.routerConnected, false);
  assert.equal(status.capability.sessionScope, 'model-only');
  current = {...current, status:'complete', completedAt:'2026-10-27T05:00:10Z', result:{overall:'unknown'}};
  const latest = await fetch(`${base}/api/quick-check`);
  assert.equal(latest.headers.get('cache-control'), 'no-store');
  assert.equal((await latest.json()).job.result.overall, 'unknown');
  await app.dispose();
  assert.equal(disposed, true);
});
