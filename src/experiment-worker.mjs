import { parentPort, workerData } from 'node:worker_threads';
import { simulate } from './simulator.mjs';
import { POLICIES, summarizeRuns } from './experiment.mjs';

try {
  const config = workerData;
  const runs = [];
  const total = POLICIES.length * config.repeats;
  for (let repeat = 0; repeat < config.repeats; repeat++) {
    // Rotate policy order between repetitions, and use the same seed for each paired comparison.
    const policies = POLICIES.slice(repeat % 3).concat(POLICIES.slice(0, repeat % 3));
    for (const policy of policies) {
      const run = simulate({ ...config, mode: policy, scenario: config.scenario === 'mixed' ? 'bidirectional' : config.scenario,
        seed: config.seed + repeat, warmupSeconds: Math.min(5, config.durationSeconds / 4), sampleIntervalMs: 1000 });
      runs.push({ ...run, policy, repeat: repeat + 1 });
      parentPort.postMessage({ progress: runs.length / total });
    }
  }
  const series = runs.filter(run => run.repeat === 1).flatMap(run => run.samples.map(sample => ({
    policy: run.policy, second: sample.timeMs / 1000, rttMs: sample.rttMs,
    meetingLossPct: sample.meetingLossPct, backgroundMbps: sample.roommateThroughputMbps,
  })));
  parentPort.postMessage({ result: { engine: 'discrete-event-model', config, runs, summary: summarizeRuns(runs, config.scenario), series,
    limitations: ['This is a deterministic queue/transport model, not Linux CAKE or physical router telemetry.',
      'Fixed-rate UDP traffic approximates transport demand; it does not emulate WebRTC codecs, adaptation, or subjective video quality.',
      'The table averages per-run summaries; p95 values are means of per-run p95, not a pooled percentile.',
      'Throughput is the sum of upload and download where both directions are active. The chart shows repetition one.'] } });
} catch (error) { parentPort.postMessage({ error: error.message }); }
