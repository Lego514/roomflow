import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MAX_OUTPUT = 256 * 1024;
const STATES = new Set(['ok', 'attention', 'unknown']);
const LAYERS = ['gateway', 'internet', 'dns', 'service'];
const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const isTime = value => typeof value === 'string' && /^\d{4}-\d\d-\d\dT/.test(value) && Number.isFinite(Date.parse(value));
const numberOrNull = value => value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1e9);

// Reconstruct only allowed fields. Even a faulty helper cannot expose raw probe
// endpoints, SSIDs, machine names, exception messages or arbitrary extra fields.
export function validateQuickCheckResult(value) {
  if (!isRecord(value) || value.scope !== 'server-host' || !isTime(value.observedAt)
      || !STATES.has(value.overall) || typeof value.historySaved !== 'boolean'
      || !Array.isArray(value.layers) || value.layers.length !== LAYERS.length) throw new Error('Invalid quick check.');
  const layers = LAYERS.map(id => {
    const rows = value.layers.filter(row => isRecord(row) && row.id === id);
    if (rows.length !== 1) throw new Error('Invalid layer.');
    const row = rows[0];
    if (!STATES.has(row.status) || !numberOrNull(row.p95Ms)
        || !Number.isInteger(row.attempts) || row.attempts < 0 || row.attempts > 1000
        || !Number.isInteger(row.failed) || row.failed < 0 || row.failed > row.attempts
        || (!row.attempts && (row.status !== 'unknown' || row.p95Ms !== null))
        || (row.failed === row.attempts && row.p95Ms !== null)
        || (row.status === 'ok' && (!row.attempts || row.failed || row.p95Ms === null))
        || (row.failed > 0 && row.status === 'ok')) throw new Error('Invalid counts.');
    return { id, status: row.status, p95Ms: row.p95Ms, attempts: row.attempts, failed: row.failed };
  });
  let wifi = null;
  if (value.wifi !== null) {
    const w = value.wifi;
    if (!isRecord(w) || typeof w.available !== 'boolean' || !STATES.has(w.status)
        || !(w.signalPct === null || (Number.isFinite(w.signalPct) && w.signalPct >= 0 && w.signalPct <= 100))
        || (!w.available && (w.status !== 'unknown' || w.signalPct !== null))) throw new Error('Invalid Wi-Fi.');
    wifi = { available: w.available, status: w.status, signalPct: w.signalPct };
  }
  const statuses = [...layers.map(row => row.status), ...(wifi?.available ? [wifi.status] : [])];
  const overall = statuses.includes('attention') ? 'attention' : statuses.includes('unknown') ? 'unknown' : 'ok';
  if (overall !== value.overall) throw new Error('Inconsistent conclusion.');
  return { scope: 'server-host', observedAt: value.observedAt, overall, layers, wifi,
    historySaved: value.historySaved, p95Basis: 'maximum-target-p95', probeCount: 3 };
}

export class QuickCheckController {
  constructor({ dataDir, rootDir = ROOT, now = Date.now, spawnProcess = spawn,
    timeoutMs = 75000, pythonCommand = process.env.ROOMFLOW_PYTHON || 'python' } = {}) {
    if (typeof dataDir !== 'string' || !dataDir || typeof pythonCommand !== 'string' || !pythonCommand
        || !Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new Error('Invalid quick-check configuration.');
    this.dataDir = path.resolve(dataDir);
    this.rootDir = path.resolve(rootDir);
    this.now = now;
    this.spawnProcess = spawnProcess;
    this.timeoutMs = timeoutMs;
    this.pythonCommand = pythonCommand;
    this.jobs = new Map();
    this.active = null;
    this.closing = false;
  }

  get(id) {
    const job = id === undefined ? [...this.jobs.values()].at(-1) : this.jobs.get(id);
    return job ? structuredClone(job) : null;
  }

  start() {
    if (this.closing) { const error = new Error('Quick check is unavailable.'); error.status = 503; throw error; }
    if (this.active) {
      const error = new Error('A quick check is already running.');
      error.status = 409; error.job = this.get(this.active.job.id); throw error;
    }
    const job = { id: randomUUID(), status: 'running', startedAt: new Date(this.now()).toISOString(),
      completedAt: null, errorCode: null, result: null };
    this.jobs.set(job.id, job);
    while (this.jobs.size > 20) this.jobs.delete(this.jobs.keys().next().value);
    const active = { job, child: null, timer: null, stdout: '', bytes: 0, done: null, finish: null, terminating: null };
    active.done = new Promise(resolve => { active.finish = resolve; });
    this.active = active;
    const fail = code => {
      if (job.status !== 'running') return;
      job.status = 'failed'; job.completedAt = new Date(this.now()).toISOString(); job.errorCode = code;
    };
    active.fail = fail;
    const release = () => {
      clearTimeout(active.timer);
      if (this.active === active) this.active = null;
      active.finish();
    };
    try {
      const child = this.spawnProcess(this.pythonCommand,
        [path.join(this.rootDir, 'scripts', 'quick-check.py'), '--data-dir', this.dataDir],
        { cwd: this.rootDir, shell: false, windowsHide: true, detached: process.platform !== 'win32',
          stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' } });
      active.child = child;
      child.stdout.on('data', chunk => {
        active.bytes += Buffer.byteLength(chunk);
        if (active.bytes > MAX_OUTPUT) {
          fail('output-limit'); this.terminate(active);
        } else if (job.status === 'running') active.stdout += chunk.toString('utf8');
      });
      // Drain stderr without keeping or exposing raw platform/network details.
      child.stderr.on('data', () => {});
      child.once('error', () => { fail('python-unavailable'); release(); });
      child.once('close', code => {
        if (job.status === 'running') {
          if (code !== 0) fail('probe-failed');
          else {
            try {
              job.result = validateQuickCheckResult(JSON.parse(active.stdout));
              job.status = 'complete'; job.completedAt = new Date(this.now()).toISOString();
            } catch { fail('invalid-result'); }
          }
        }
        release();
      });
      active.timer = setTimeout(() => { fail('timeout'); this.terminate(active); }, this.timeoutMs);
      active.timer.unref?.();
    } catch { fail('python-unavailable'); release(); }
    return this.get(job.id);
  }

  terminate(active) {
    if (active.terminating) return active.terminating;
    active.terminating = (async () => {
      const child = active.child;
      if (!child) return;
      if (Number.isInteger(child.pid) && child.pid > 0) {
        if (process.platform === 'win32') {
          await new Promise(resolve => {
            try {
              const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'],
                { shell: false, windowsHide: true, stdio: 'ignore' });
              let settled = false;
              const finish = fallback => {
                if (settled) return;
                settled = true; clearTimeout(killTimer);
                if (fallback) { try { child.kill?.('SIGKILL'); } catch {} }
                resolve();
              };
              const killTimer = setTimeout(() => {
                try { killer.kill('SIGKILL'); } catch {}
                finish(true);
              }, 5000);
              killer.once('error', () => finish(true));
              killer.once('close', code => finish(Boolean(code)));
            } catch { child.kill?.('SIGKILL'); resolve(); }
          });
        } else {
          try { process.kill(-child.pid, 'SIGKILL'); }
          catch { try { child.kill('SIGKILL'); } catch {} }
        }
      } else {
        try { child.kill?.('SIGKILL'); } catch {}
      }
    })();
    return active.terminating;
  }

  async dispose() {
    this.closing = true;
    const active = this.active;
    if (!active) return;
    active.fail('interrupted');
    clearTimeout(active.timer);
    await this.terminate(active);
    // Process close normally arrives immediately after tree termination. Bound
    // shutdown even if a platform helper fails to report its close event.
    let timer;
    await Promise.race([active.done, new Promise(resolve => { timer = setTimeout(resolve, 3000); })]);
    clearTimeout(timer);
  }
}
