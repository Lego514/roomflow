import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { Worker } from 'node:worker_threads';
import { SessionController, atomicJson } from './session.mjs';
import { validateExperiment, resultCsv } from './experiment.mjs';
import { simulate } from './simulator.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml' };

export function createApp({ dataDir = path.join(ROOT, 'data'), evidenceDir = path.join(ROOT, 'results', 'linux'), now = Date.now } = {}) {
  fs.mkdirSync(path.join(dataDir, 'experiments'), { recursive: true });
  let appliedMode = 'normal';
  let preview = null;
  const session = new SessionController({ file: path.join(dataDir, 'session.json'), now,
    apply: mode => {
      const result = simulate({ mode: mode === 'meeting' ? 'priority' : 'fair', scenario:'mixed',
        durationSeconds:5, warmupSeconds:1, seed:42, upMbps:5, downMbps:20, baseRttMs:40 });
      preview = { scope:'fixed-workload-model', config:result.config, summary:result.summary };
      appliedMode = mode;
    }, read: () => preview?.config.mode === 'priority' ? 'meeting' : preview?.config.mode === 'fair' ? 'normal' : 'unknown' });
  const jobs = new Map();
  const workers = new Set();
  let closing = false;
  const metaPath = id => path.join(dataDir, 'experiments', `${id}.meta.json`);
  const resultPath = id => path.join(dataDir, 'experiments', `${id}.json`);
  const saveJob = job => atomicJson(metaPath(job.id), job);
  // Persistence can also fail inside worker event callbacks. Keep that failure
  // visible in memory without letting an uncaught EventEmitter callback crash HTTP.
  const failJob = (job, message) => {
    job.status = 'failed'; job.error = message;
    try { saveJob(job); }
    catch (error) { job.error = `${message} Metadata could not be persisted: ${error.message}`; }
  };
  for (const entry of fs.readdirSync(path.join(dataDir, 'experiments'))) {
    if (!/^[a-f0-9-]+\.meta\.json$/.test(entry)) continue;
    const job = JSON.parse(fs.readFileSync(path.join(dataDir, 'experiments', entry), 'utf8'));
    if (['running', 'queued'].includes(job.status)) {
      failJob(job, 'The experiment was interrupted by a server restart; start a new run.');
    } else if (job.status === 'complete' && !fs.existsSync(resultPath(job.id))) {
      failJob(job, 'The saved experiment result is missing; start a new run.');
    }
    jobs.set(job.id, job);
  }
  let expiryError = null;
  const timer = setInterval(() => {
    try { session.status(); expiryError = null; }
    catch (error) { expiryError = error.message; }
  }, 200);
  timer.unref();
  const json = (res, status, value) => {
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(value));
  };
  const body = async req => {
    if (!(req.headers['content-type'] ?? '').startsWith('application/json')) {
      const e = new Error('Use application/json.'); e.status = 415; throw e;
    }
    let text = '';
    for await (const chunk of req) {
      text += chunk;
      if (Buffer.byteLength(text) > 16384) { const e = new Error('Request body too large.'); e.status = 413; throw e; }
    }
    try { return JSON.parse(text); } catch { throw new Error('Invalid JSON.'); }
  };
  const server = http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'");
    try {
      if (closing) return json(res, 503, { error: 'The server is shutting down.' });
      const host = req.headers.host ?? '';
      if (!/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(host)) return json(res, 403, { error: 'Use the localhost address.' });
      if (req.method === 'POST' && req.headers.origin && req.headers.origin !== `http://${host}`) {
        return json(res, 403, { error: 'Cross-origin writes are not allowed.' });
      }
      const url = new URL(req.url, `http://${host}`);
      if (req.method === 'GET' && url.pathname === '/api/status') {
        return json(res, 200, { session: session.status(), policies: ['fifo', 'fair', 'priority'],
          capability: { engine: 'model', kernelAvailable: false, sessionScope: 'model-only', effectivePolicy: appliedMode === 'meeting' ? 'priority' : 'fair' }, preview, expiryError });
      }
      if (req.method === 'GET' && url.pathname === '/api/kernel-evidence') {
        const file = path.join(evidenceDir, 'summary.json');
        if (!fs.existsSync(file)) return json(res, 200, { status:'pending', engine:'linux-kernel', message:'Linux 重複實驗尚在執行' });
        try {
          const evidence = JSON.parse(fs.readFileSync(file, 'utf8'));
          if (!evidence || evidence.engine !== 'linux-kernel' || evidence.status !== 'verified' || !Array.isArray(evidence.summary)) {
            throw new Error('Invalid saved kernel evidence.');
          }
          return json(res, 200, evidence);
        }
        catch { return json(res, 503, { error:'Linux experiment evidence is temporarily unavailable; retry shortly.' }); }
      }
      if (req.method === 'GET' && url.pathname === '/api/kernel-evidence/export.csv') {
        const file = path.join(evidenceDir, 'batch', 'measurements.csv');
        if (!fs.existsSync(file) || !fs.statSync(file).isFile()) return json(res, 404, { error:'Linux experiment CSV is not available yet.' });
        res.writeHead(200, { 'Content-Type':'text/csv; charset=utf-8', 'Content-Disposition':'attachment; filename="roomflow-linux-measurements.csv"', 'Cache-Control':'no-store' });
        const stream = fs.createReadStream(file);
        stream.on('error', () => res.destroy());
        stream.pipe(res);
        return;
      }
      if (req.method === 'POST' && url.pathname === '/api/session') {
        const command = await body(req);
        if (!command || typeof command !== 'object') throw new Error('Invalid session command.');
        const value = command.action === 'start' ? session.start(command) : command.action === 'stop' ? session.stop() : null;
        if (!value) throw new Error('Unknown session action.');
        return json(res, 200, { session: value, scope: 'model-only', effectivePolicy: appliedMode === 'meeting' ? 'priority' : 'fair' });
      }
      if (req.method === 'GET' && url.pathname === '/api/experiments') {
        return json(res, 200, { experiments: [...jobs.values()].sort((a,b) => b.createdAt - a.createdAt).slice(0,20) });
      }
      if (req.method === 'POST' && url.pathname === '/api/experiments') {
        const config = validateExperiment(await body(req));
        if (workers.size) return json(res, 409, { error: 'An experiment is already running. Wait for it to finish.' });
        const job = { id: randomUUID(), status: 'queued', progress: 0, config, scenario: config.scenario, createdAt: now() };
        jobs.set(job.id, job); saveJob(job);
        const worker = new Worker(new URL('./experiment-worker.mjs', import.meta.url), { workerData: config });
        workers.add(worker); job.status = 'running'; saveJob(job);
        worker.on('message', message => {
          try {
            if (message.progress !== undefined) { job.progress = message.progress; }
            if (message.result) { atomicJson(resultPath(job.id), message.result); job.status = 'complete'; job.progress = 1; job.completedAt = now(); }
            if (message.error) { job.status = 'failed'; job.error = message.error; }
            saveJob(job);
          } catch (error) { failJob(job, `Could not persist experiment: ${error.message}`); }
        });
        worker.on('error', error => { failJob(job, error.message); });
        worker.on('exit', code => {
          workers.delete(worker);
          if (!['complete','failed'].includes(job.status)) failJob(job, `Experiment worker exited (${code}) without a result.`);
        });
        return json(res, 202, { id: job.id, status: 'queued' });
      }
      const match = /^\/api\/experiments\/([a-f0-9-]+)(?:\/(export\.json|export\.csv))?$/.exec(url.pathname);
      if (req.method === 'GET' && match) {
        const job = jobs.get(match[1]);
        if (!job) return json(res, 404, { error: 'Experiment not found.' });
        let result;
        if (job.status === 'complete') {
          try {
            result = JSON.parse(fs.readFileSync(resultPath(job.id), 'utf8'));
            if (!result || result.engine !== 'discrete-event-model' || !Array.isArray(result.runs) || !result.runs.length || !Array.isArray(result.summary)) {
              throw new Error('Invalid saved experiment result.');
            }
          }
          catch (error) { failJob(job, `The saved experiment result could not be loaded: ${error.message}`); }
          if (job.status !== 'complete') result = undefined;
        }
        if (match[2]) {
          if (!result) return json(res, 409, { error: 'Export is available after successful completion.' });
          res.setHeader('Content-Disposition', `attachment; filename="roomflow-${job.id}.${match[2].endsWith('csv') ? 'csv' : 'json'}"`);
          if (match[2] === 'export.csv') { res.writeHead(200, { 'Content-Type': 'text/csv; charset=utf-8' }); res.end(resultCsv(result)); return; }
          return json(res, 200, result);
        }
        return json(res, 200, { ...job, result });
      }
      if (req.method !== 'GET') return json(res, 405, { error: 'Method not allowed.' });
      const relative = url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname).slice(1);
      const file = path.resolve(ROOT, 'public', relative);
      const publicDir = `${path.join(ROOT, 'public')}${path.sep}`;
      if (!file.startsWith(publicDir) || !MIME[path.extname(file)] || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
        return json(res, 404, { error: 'Not found.' });
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(file)], 'Cache-Control': 'no-cache' });
      fs.createReadStream(file).pipe(res);
    } catch (error) { if (!res.headersSent) json(res, error.status ?? 400, { error: error.message }); else res.end(); }
  });
  const dispose = async () => {
    closing = true;
    clearInterval(timer);
    const closed = server.listening ? new Promise(resolve => server.close(resolve)) : Promise.resolve();
    await Promise.all([...workers].map(worker => worker.terminate()));
    await closed;
  };
  return { server, session, dispose };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.ROOMFLOW_PORT ?? 3210);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid ROOMFLOW_PORT.');
  const app = createApp();
  app.server.listen(port, '127.0.0.1', () => console.log(`RoomFlow: http://127.0.0.1:${port} (model dashboard)`));
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => { await app.dispose(); process.exit(0); });
}
