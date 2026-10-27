import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { QuickCheckController, validateQuickCheckResult } from '../src/quick-check.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fixture = () => ({ scope: 'server-host', observedAt: '2026-10-27T05:00:00.000Z', overall: 'ok',
  layers: ['gateway', 'internet', 'dns', 'service'].map(id => ({ id, status: 'ok', p95Ms: 12, attempts: 3, failed: 0 })),
  wifi: { available: false, status: 'unknown', signalPct: null }, historySaved: true });

function harness(t, options = {}) {
  const children = [];
  const calls = [];
  const controller = new QuickCheckController({ dataDir: path.join(ROOT, 'data'),
    spawnProcess: (...args) => {
      calls.push(args);
      const child = new EventEmitter();
      child.stdout = new EventEmitter(); child.stderr = new EventEmitter();
      child.kill = signal => { child.killed = signal; queueMicrotask(() => child.emit('close', null)); return true; };
      children.push(child);
      return child;
    }, ...options });
  t.after(() => controller.dispose());
  return { controller, children, calls };
}

function complete(child, result = fixture(), code = 0) {
  child.stdout.emit('data', Buffer.from(typeof result === 'string' ? result : JSON.stringify(result)));
  child.emit('close', code);
}

test('one fixed local probe job at a time; safe process options; no getter side effects', t => {
  const { controller, children, calls } = harness(t);
  assert.equal(controller.get(), null);
  assert.equal(calls.length, 0);
  const job = controller.start();
  assert.equal(job.status, 'running');
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], process.env.ROOMFLOW_PYTHON || 'python');
  assert.deepEqual(calls[0][1], [path.join(ROOT, 'scripts', 'quick-check.py'), '--data-dir', path.join(ROOT, 'data')]);
  assert.equal(calls[0][2].shell, false);
  assert.equal(calls[0][2].windowsHide, true);
  assert.throws(() => controller.start(), error => error.status === 409 && error.job.id === job.id);
  assert.equal(calls.length, 1);
  complete(children[0]);
  assert.equal(controller.get(job.id).status, 'complete');
  assert.equal(controller.get(job.id).result.overall, 'ok');
  assert.equal(controller.get('missing'), null);
});

test('attention, unavailable layers, partial history failure and privacy filtering stay distinct', t => {
  const { controller, children } = harness(t);
  const result = fixture();
  result.overall = 'attention'; result.historySaved = false;
  result.layers[0] = { id: 'gateway', status: 'unknown', p95Ms: null, attempts: 0, failed: 0 };
  result.layers[1].status = 'attention'; result.layers[1].failed = 1;
  result.privateAddress = '192.0.2.1'; result.error = 'C:\\private\\secret';
  result.layers[1].target = 'sensitive-host.invalid';
  const job = controller.start(); complete(children[0], result);
  const saved = controller.get(job.id);
  assert.equal(saved.status, 'complete');
  assert.equal(saved.result.overall, 'attention');
  assert.equal(saved.result.historySaved, false);
  assert.equal(saved.result.layers[0].status, 'unknown');
  assert.doesNotMatch(JSON.stringify(saved), /192\.0\.2|sensitive-host|private|secret/);
  saved.result.layers[0].status = 'ok';
  assert.equal(controller.get(job.id).result.layers[0].status, 'unknown');
  const unknown = fixture(); unknown.layers[0] = result.layers[0]; unknown.overall = 'unknown';
  assert.equal(validateQuickCheckResult(unknown).overall, 'unknown');
});

test('invalid output, inconsistent success, counts, duplicate layers and exceptions cannot pass', t => {
  const { controller, children } = harness(t);
  const invalid = ['not-json', {}, { ...fixture(), overall: 'unknown' }];
  const falseOk = fixture(); falseOk.layers[0].failed = 1; invalid.push(falseOk);
  const missing = fixture(); missing.layers[0].attempts = 0; invalid.push(missing);
  const duplicate = fixture(); duplicate.layers[1].id = 'gateway'; invalid.push(duplicate);
  const nonsense = fixture(); nonsense.layers[1].p95Ms = -1; invalid.push(nonsense);
  const overflow = fixture(); overflow.layers[1].failed = 4; invalid.push(overflow);
  const disconnectedWifi = fixture(); disconnectedWifi.wifi = { available: false, status: 'ok', signalPct: 99 }; invalid.push(disconnectedWifi);
  for (const result of invalid) {
    const job = controller.start(); complete(children.at(-1), result);
    assert.equal(controller.get(job.id).status, 'failed');
    assert.equal(controller.get(job.id).errorCode, 'invalid-result');
    assert.equal(controller.get(job.id).result, null);
  }
});

test('missing Python and nonzero probe exit return generic errors', t => {
  const { controller, children } = harness(t);
  const first = controller.start();
  children[0].emit('error', new Error('ENOENT C:\\private\\python.exe'));
  assert.equal(controller.get(first.id).errorCode, 'python-unavailable');
  assert.doesNotMatch(JSON.stringify(controller.get()), /ENOENT|private/);
  const second = controller.start(); complete(children[1], { errorCode: 'probe-failed' }, 1);
  assert.equal(controller.get(second.id).errorCode, 'probe-failed');
});

test('output limit terminates the child and never publishes a result', async t => {
  const { controller, children } = harness(t);
  const job = controller.start(); children[0].stdout.emit('data', Buffer.alloc(256 * 1024 + 1));
  assert.equal(controller.get(job.id).errorCode, 'output-limit');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(children[0].killed, 'SIGKILL');
  assert.equal(controller.get(job.id).result, null);
});

test('wall-clock deadline and shutdown terminate running work', async t => {
  const { controller, children } = harness(t, { timeoutMs: 10 });
  const timed = controller.start();
  await new Promise(resolve => setTimeout(resolve, 30));
  assert.equal(controller.get(timed.id).errorCode, 'timeout');
  assert.equal(children[0].killed, 'SIGKILL');
  const stopped = controller.start(); await controller.dispose();
  assert.equal(children[1].killed, 'SIGKILL');
  assert.equal(controller.get(stopped.id).errorCode, 'interrupted');
  assert.throws(() => controller.start(), error => error.status === 503);
});

test('bounded in-memory history keeps the latest twenty jobs', t => {
  const { controller, children } = harness(t);
  const first = controller.start(); complete(children[0]);
  let latest;
  for (let i = 0; i < 21; i++) { latest = controller.start(); complete(children.at(-1)); }
  assert.equal(controller.get(first.id), null);
  assert.equal(controller.get().id, latest.id);
  assert.equal(controller.jobs.size, 20);
});

test('Python bridge classifies and stores mocked probes without performing network traffic', () => {
  const script = String.raw`
import importlib.util, json, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
root = Path(sys.argv[1]); sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location('quick_bridge', root / 'scripts' / 'quick-check.py')
bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)
from homenet.stats import Series
def series(values):
    s = Series('private-target.invalid')
    for value in values: s.add(value)
    return s
r = SimpleNamespace(wifi=None, layers={name:[series([10,11,12])] for name in ('gateway','internet','dns','service')}, statuses={name:'ok' for name in ('gateway','internet','dns','service')}, verdict=('ok',None))
(root / 'data').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=root / 'data') as tmp:
    with patch.object(bridge, 'run_check', return_value=r) as collect:
        result = bridge.collect(Path(tmp))
    collect.assert_called_once_with(count=3)
    assert result['overall'] == 'ok' and result['historySaved']
    assert (Path(tmp)/'observations.json').is_file()
    with patch.object(bridge, 'run_check', return_value=r), patch.object(bridge.store,'connect',side_effect=OSError('private')):
        assert bridge.collect(Path(tmp))['historySaved'] is False
r.layers['gateway']=[]; r.statuses['gateway']='down'
assert bridge.summarize(r,'2026-10-27T05:00:00Z')['overall']=='unknown'
r.layers['internet']=[series([None,None,None])]; r.statuses['internet']='down'
summary = bridge.summarize(r,'2026-10-27T05:00:00Z')
assert summary['overall']=='attention' and summary['layers'][1]['failed']==3
assert 'private-target' not in json.dumps(summary)
print('mock bridge and persistence passed')
`;
  const output = execFileSync(process.env.ROOMFLOW_PYTHON || 'python', ['-c', script, ROOT],
    { encoding: 'utf8', windowsHide: true, timeout: 15000 });
  assert.match(output, /mock bridge and persistence passed/);
});
