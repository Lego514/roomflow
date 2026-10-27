import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { validateObservations } from '../src/observations.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sha = text => createHash('sha256').update(text).digest('hex');

test('portable demonstration has self-contained assets, valid saved sources, and reproducible provenance', () => {
  const html = fs.readFileSync(path.join(root, 'artifacts/demo/RoomFlow.html'), 'utf8');
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'artifacts/demo/manifest.json'), 'utf8'));
  assert.equal(sha(html), manifest.outputSHA256, 'rebuild the portable artifact after editing its evidence or UI');
  assert.doesNotMatch(html, /<(?:script|link)[^>]+(?:src|href)=["'][^"']+["']/i, 'portable assets must be embedded');
  assert.doesNotMatch(html, /<iframe|@import\b|url\(["']?https?:/i, 'offline display must not need another page or a remote asset');
  const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(match => match[1]);
  assert.equal(scripts.length, 2);
  for (const script of scripts) new vm.Script(script);
  const context = { window: {} };
  // Only the generated data-assignment script is evaluated here. No browser,
  // DOM, network, or local collector is invoked by this portable-file check.
  vm.runInNewContext(scripts[0], context, { timeout: 1000 });
  const sources = context.window.ROOMFLOW_OFFLINE_SOURCES;
  assert.ok(sources.demo);
  assert.equal(context.window.ROOMFLOW_OFFLINE_DATA, sources.demo);
  assert.equal(sources.demo.source.kind, 'historical-demo');
  assert.ok(sources.demo.timeline.length >= 1000);
  for (const [key, payload] of Object.entries(sources)) {
    validateObservations(payload, key === 'demo' ? 'historical-demo' : 'lab-drill');
    assert.equal(payload.monitor.status, 'historical');
    assert.notEqual(payload.source.kind, 'local-history');
    if (key !== 'demo') {
      assert.equal(payload.incidents.length, 1);
      assert.equal(payload.incidents[0].status, 'resolved');
      assert.equal(payload.notifications.length, 2);
      assert.equal(payload.replay.available, true);
      assert.deepEqual(Array.from(payload.replay.frames, frame => frame.stage), ['normal', 'normal', 'pending', 'pending', 'open', 'recovering', 'resolved']);
      assert.equal(payload.replay.frames[3].incidents.length, 0, 'two abnormalities must not reveal a future confirmed event');
      assert.equal(payload.replay.frames[4].incidents[0].status, 'open');
      assert.equal(payload.replay.frames[5].incidents[0].status, 'open', 'one healthy check cannot reveal final recovery');
      assert.equal(payload.replay.frames[5].notifications.length, 1);
      assert.equal(payload.incidents[0].evidence.checkCount, 3);
      assert.equal(payload.incidents[0].evidence.layers.gateway.failed, 0);
    }
  }
  for (const [relative, expected] of Object.entries(manifest.inputSHA256)) {
    assert.equal(sha(fs.readFileSync(path.join(root, relative), 'utf8')), expected);
  }
  for (const relative of ['public/monitor.css', 'public/monitor.js', 'public/monitor.html']) assert.ok(manifest.inputSHA256[relative]);
  assert.ok(html.indexOf('id="observations"') < html.lastIndexOf('<script>'), 'UI must run after its DOM mount exists');
  assert.equal(manifest.requiresNetwork, false);
  assert.equal(manifest.includesLocalPrivateHistory, false);
});
