import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { SessionController } from '../src/session.mjs';

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'roomflow-session-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  let time = 100000, applied = 'normal', fail = false;
  const options = { file: path.join(dir, 'session.json'), now: () => time,
    apply: mode => { if (fail && mode === 'meeting') throw new Error('injected adapter failure'); applied = mode; }, read: () => applied };
  const controller = new SessionController(options);
  return { controller, options, advance: n => { time += n; }, fail: () => { fail = true; }, mode: () => applied };
}

test('lease expiry restores normal mode and survives reconstruction', t => {
  const f = fixture(t);
  f.controller.start({ durationSeconds: 10, device: 'meeting' });
  assert.equal(f.mode(), 'meeting');
  f.advance(5000);
  assert.equal(new SessionController(f.options).status().mode, 'meeting');
  f.advance(5000);
  const restored = new SessionController(f.options).status();
  assert.equal(restored.mode, 'normal');
  assert.equal(restored.expiresAt, null);
  assert.equal(f.mode(), 'normal');
  assert.equal(restored.revision, 2);
});

test('early stop restores state, is idempotent, and a second start conflicts', t => {
  const f = fixture(t);
  f.controller.start({ durationSeconds: 60, device: 'meeting' });
  assert.throws(() => f.controller.start({ durationSeconds: 5, device: 'meeting' }), /already active/);
  assert.equal(f.controller.stop().mode, 'normal');
  assert.equal(f.controller.stop().revision, 2);
});

test('apply failure returns error, rolls back, and does not persist false success', t => {
  const f = fixture(t); f.fail();
  assert.throws(() => f.controller.start({ durationSeconds: 5, device: 'meeting' }), /could not be applied/);
  assert.equal(f.controller.status().mode, 'normal');
  assert.equal(f.mode(), 'normal');
  assert.equal(fs.existsSync(f.options.file), false);
});

test('invalid device and duration are rejected without mutation', t => {
  const f = fixture(t);
  for (const durationSeconds of [0, -1, 7201, 1.5, '60', Infinity]) {
    assert.throws(() => f.controller.start({ durationSeconds, device: 'meeting' }));
  }
  assert.throws(() => f.controller.start({ durationSeconds: 5, device: 'roommate' }));
  assert.equal(f.controller.status().revision, 0);
});

test('readback mismatch cannot be reported as successful start', t => {
  const f = fixture(t);
  const controller = new SessionController({ ...f.options, apply: () => {}, read: () => 'normal' });
  assert.throws(() => controller.start({ durationSeconds: 5, device: 'meeting' }), /readback/);
  assert.equal(controller.status().mode, 'normal');
});

test('expiry persistence failure rolls back, reports failure, and retries safely', t => {
  const f = fixture(t);
  f.controller.start({ durationSeconds: 5, device: 'meeting' });
  const persisted = fs.readFileSync(f.options.file, 'utf8');
  // A directory at the atomic-write temp path fails on Windows and Unix even
  // when tests run as a privileged user; no permission assumptions are needed.
  fs.mkdirSync(`${f.options.file}.tmp`);
  f.advance(6000);
  assert.throws(() => f.controller.status(), /could not be applied/);
  assert.equal(f.mode(), 'meeting');
  assert.equal(fs.readFileSync(f.options.file, 'utf8'), persisted);
  fs.rmdirSync(`${f.options.file}.tmp`);
  const restored = f.controller.status();
  assert.equal(restored.mode, 'normal');
  assert.equal(restored.revision, 2);
  assert.equal(f.mode(), 'normal');
  assert.equal(JSON.parse(fs.readFileSync(f.options.file, 'utf8')).mode, 'normal');
});
