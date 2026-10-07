export const POLICIES = ['fifo', 'fair', 'priority'];
export const SCENARIOS = ['idle', 'upload', 'download', 'mixed'];

export function validateExperiment(input = {}) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Experiment configuration must be an object.');
  const result = { scenario: input.scenario ?? 'mixed', durationSeconds: input.durationSeconds ?? 60,
    repeats: input.repeats ?? 3, seed: input.seed ?? 42, upMbps: input.upMbps ?? 5,
    downMbps: input.downMbps ?? 20, baseRttMs: input.baseRttMs ?? 40 };
  if (!SCENARIOS.includes(result.scenario)) throw new Error('Unknown scenario.');
  for (const [name, min, max, integer] of [
    ['durationSeconds', 5, 180, true], ['repeats', 1, 5, true], ['seed', 0, 2147483647, true],
    ['upMbps', 2, 100, false], ['downMbps', 3, 100, false], ['baseRttMs', 1, 300, false],
  ]) {
    const v = result[name];
    if (typeof v !== 'number' || !Number.isFinite(v) || v < min || v > max || (integer && !Number.isInteger(v))) {
      throw new Error(`${name} must be ${integer ? 'an integer' : 'a number'} between ${min} and ${max}.`);
    }
  }
  return result;
}

export function summarizeRuns(runs, scenario) {
  return POLICIES.map(policy => {
    const selected = runs.filter(run => run.policy === policy);
    const mean = field => {
      const values = selected.map(run => run.summary[field]);
      if (!values.length || values.some(value => typeof value !== 'number' || !Number.isFinite(value))) return null;
      return values.reduce((sum, value) => sum + value, 0) / values.length;
    };
    return { policy, scenario, repeats: selected.length,
      meetingRttP95Ms: mean('rttP95Ms'), meetingJitterMs: mean('meetingJitterMs'), meetingLossPct: mean('meetingLossPct'),
      meetingMbps: mean('meetingReceivedMbps'), backgroundMbps: mean('roommateThroughputMbps') };
  });
}

export function resultCsv(result) {
  const rows = ['engine,policy,scenario,repeat,seed,p95_rtt_ms,jitter_ms,meeting_loss_pct,meeting_mbps,background_mbps'];
  for (const run of result.runs) {
    rows.push(['discrete-event-model',run.policy,result.config.scenario,run.repeat,run.config.seed,
      run.summary.rttP95Ms,run.summary.meetingJitterMs,run.summary.meetingLossPct,
      run.summary.meetingReceivedMbps,run.summary.roommateThroughputMbps].join(','));
  }
  return `${rows.join('\n')}\n`;
}
