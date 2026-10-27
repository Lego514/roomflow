import fs from 'node:fs';
import path from 'node:path';

const KINDS = { demo: 'historical-demo', local: 'local-history', drill: 'lab-drill' };
const SCENARIOS = new Set(['delay', 'loss', 'dns']);
const MAX_BYTES = 24 * 1024 * 1024;
const validTime = value => typeof value === 'string' && Number.isFinite(Date.parse(value));
const nonnegative = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const optionalNumber = value => value === null || value === undefined || nonnegative(value);
const LAYERS = ['gateway', 'internet', 'dns', 'service'];

function validateIncident(incident, cutoff = Infinity) {
  if (!incident || typeof incident.id !== 'string' || !['open', 'resolved'].includes(incident.status)
      || !validTime(incident.startedAt) || !validTime(incident.openedAt)
      || !Array.isArray(incident.affectedLayers) || !Array.isArray(incident.observations)
      || !Array.isArray(incident.unknowns) || !Array.isArray(incident.nextChecks)
      || (incident.status === 'resolved' && !validTime(incident.resolvedAt))) throw new Error('Invalid incident.');
  for (const key of ['startedAt', 'openedAt', 'lastObservedAt', 'lastAbnormalAt', 'resolvedAt']) {
    if (incident[key] != null && (!validTime(incident[key]) || Date.parse(incident[key]) > cutoff)) throw new Error('Incident contains future evidence.');
  }
  const evidence = incident.evidence;
  if (evidence === undefined) return; // Previously saved schema-1 exports remain readable.
  if (!evidence || !validTime(evidence.startAt) || !validTime(evidence.endAt)
      || Date.parse(evidence.startAt) !== Date.parse(incident.startedAt)
      || Date.parse(evidence.endAt) < Date.parse(evidence.startAt) || Date.parse(evidence.endAt) > cutoff
      || !Number.isInteger(evidence.checkCount) || evidence.checkCount < 1 || !evidence.layers) throw new Error('Invalid event evidence.');
  for (const name of LAYERS) {
    const layer = evidence.layers[name];
    if (!layer || typeof layer.countsComplete !== 'boolean') throw new Error('Invalid event layer evidence.');
    for (const key of ['peakP95Ms', 'latencyThresholdMs', 'failureThresholdPct', 'attempts', 'failed', 'failurePct']) {
      if (!optionalNumber(layer[key])) throw new Error('Invalid event evidence metric.');
    }
    for (const key of ['countedChecks', 'missingCountChecks', 'abnormalChecks', 'healthyChecks', 'unknownChecks', 'latencyBreaches', 'failureBreaches']) {
      if (!Number.isInteger(layer[key]) || layer[key] < 0 || layer[key] > evidence.checkCount) throw new Error('Invalid evidence check count.');
    }
    if (layer.failurePct > 100 || layer.failureThresholdPct > 100
        || (layer.attempts != null && layer.failed > layer.attempts)) throw new Error('Invalid evidence probe totals.');
    if (layer.peakP95At != null && (!validTime(layer.peakP95At)
        || Date.parse(layer.peakP95At) < Date.parse(evidence.startAt)
        || Date.parse(layer.peakP95At) > Date.parse(evidence.endAt))) throw new Error('Invalid peak observation time.');
  }
}

function validateTransitions(transitions, cutoff = Infinity) {
  if (!Array.isArray(transitions)) throw new Error('Invalid transition history.');
  const ids = new Set();
  for (const transition of transitions) {
    if (!transition || typeof transition.id !== 'string' || typeof transition.incidentId !== 'string'
        || !['opened', 'resolved'].includes(transition.type) || !validTime(transition.at)
        || Date.parse(transition.at) > cutoff || ids.has(transition.id)) throw new Error('Invalid or future transition.');
    ids.add(transition.id);
  }
}

export class ObservationError extends Error {
  constructor(message, status = 503) { super(message); this.status = status; }
}

function emptyLocal(now) {
  return {
    schemaVersion: 1,
    source: { kind: 'local-history', label: 'Local measurements', windowStart: null, windowEnd: null,
      generatedAt: null, notes: ['No local dashboard export is available. Run python -m homenet dashboard, or let the scheduled check export it.'] },
    policy: { openAfter: 3, recoverAfter: 2, maxGapSeconds: 900, staleAfterSeconds: 900 },
    latest: null, timeline: [], incidents: [], notifications: [],
    monitor: { status: 'empty', evaluatedAt: new Date(now).toISOString(), lastObservedAt: null },
  };
}

// Only curated aggregate JSON files are exposed. No database, terminal log,
// arbitrary path, or active network probe is reachable through this read API.
export function loadObservations({ source = 'demo', scenario = 'delay', dataDir, demoFile, drillDir, now = Date.now() }) {
  if (!Object.hasOwn(KINDS, source)) throw new ObservationError('Unknown observation source.', 400);
  if (source === 'drill' && !SCENARIOS.has(scenario)) throw new ObservationError('Unknown drill scenario.', 400);
  const file = source === 'local' ? path.join(dataDir, 'observations.json')
    : source === 'demo' ? demoFile : path.join(drillDir, `${scenario}.json`);
  let value;
  try {
    const stat = fs.statSync(file);
    if (!stat.isFile() || stat.size > MAX_BYTES) throw new Error('Invalid file.');
    value = JSON.parse(fs.readFileSync(file, 'utf8'));
    validateObservations(value, KINDS[source]);
  } catch (error) {
    if (error.code === 'ENOENT' && source === 'local') return emptyLocal(now);
    throw new ObservationError(source === 'local' ? 'Local measurement export is unavailable or invalid.'
      : source === 'demo' ? 'Historical measurement evidence is unavailable or invalid.'
      : 'This drill has no valid saved measurement evidence. Run the isolated Linux drill first.');
  }
  const at = value.latest?.at ?? null;
  const ageSeconds = at ? (now - Date.parse(at)) / 1000 : null;
  const staleSeconds = value.policy.staleAfterSeconds;
  const historical = source !== 'local';
  value.monitor = { ...value.monitor,
    status: historical ? 'historical' : !at ? 'empty' : ageSeconds > staleSeconds || ageSeconds < -60 ? 'stale' : 'current',
    evaluatedAt: new Date(now).toISOString(), lastObservedAt: at,
    ageSeconds: ageSeconds === null ? null : Math.max(0, ageSeconds),
    clockSkew: ageSeconds !== null && ageSeconds < -60,
  };
  return value;
}

export function validateObservations(value, kind) {
  if (!value || value.schemaVersion !== 1 || value.source?.kind !== kind
      || typeof value.source.label !== 'string' || !Array.isArray(value.source.notes)
      || !value.policy || !Number.isFinite(value.policy.staleAfterSeconds) || value.policy.staleAfterSeconds <= 0
      || !Array.isArray(value.timeline) || !Array.isArray(value.incidents) || !Array.isArray(value.notifications)) {
    throw new Error('Invalid observation schema.');
  }
  for (const sample of value.timeline) {
    if (!sample || !validTime(sample.at) || !['ok', 'degraded', 'unknown'].includes(sample.status)
        || !sample.layers || typeof sample.layers !== 'object') throw new Error('Invalid observation sample.');
    for (const layer of Object.values(sample.layers)) {
      if (!layer || !['ok', 'degraded', 'unknown'].includes(layer.status)) throw new Error('Invalid observation layer.');
      for (const metric of ['p50Ms', 'p95Ms', 'failurePct', 'attempts', 'failed']) {
        if (layer[metric] !== null && layer[metric] !== undefined && (!Number.isFinite(layer[metric]) || layer[metric] < 0)) {
          throw new Error('Invalid observation metric.');
        }
      }
      if (layer.failurePct > 100 || (layer.attempts != null && layer.failed > layer.attempts)) throw new Error('Invalid probe counts.');
    }
  }
  if (value.latest !== null && value.latest !== undefined
      && (!validTime(value.latest.at) || !value.timeline.some(sample => sample.at === value.latest.at))) {
    throw new Error('Latest observation is missing from the timeline.');
  }
  for (const incident of value.incidents) validateIncident(incident);
  validateTransitions(value.notifications);
  if (value.replay !== undefined) {
    const replay = value.replay;
    if (kind !== 'lab-drill' || !replay || !Array.isArray(replay.frames)
        || !Number.isInteger(replay.totalSamples) || replay.totalSamples !== (value.timelineTotal ?? value.timeline.length)
        || typeof replay.available !== 'boolean') throw new Error('Invalid replay metadata.');
    if (replay.available && (replay.frames.length !== replay.totalSamples || replay.totalSamples !== value.timeline.length)) throw new Error('Incomplete replay frames.');
    if (!replay.available && replay.frames.length) throw new Error('Unavailable replay must not contain frames.');
    for (let index = 0; index < replay.frames.length; index++) {
      const frame = replay.frames[index];
      if (!frame || frame.sampleCount !== index + 1 || frame.at !== value.timeline[index].at
          || !['normal', 'pending', 'open', 'recovering', 'resolved', 'unknown'].includes(frame.stage)
          || !Array.isArray(frame.incidents)
          || !Number.isInteger(frame.pendingAbnormalChecks) || frame.pendingAbnormalChecks < 0
          || !Number.isInteger(frame.pendingRecoveryChecks) || frame.pendingRecoveryChecks < 0) throw new Error('Invalid replay frame.');
      const cutoff = Date.parse(frame.at);
      for (const incident of frame.incidents) validateIncident(incident, cutoff);
      validateTransitions(frame.notifications, cutoff);
    }
  }
  return value;
}
