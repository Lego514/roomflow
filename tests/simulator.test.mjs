import test from 'node:test';
import assert from 'node:assert/strict';
import { simulate, normalizeConfig, percentile } from '../src/simulator.mjs';

const fast = { durationSeconds: 12, warmupSeconds: 2 };
const sum = (object) => Object.values(object).reduce((a, b) => a + b, 0);

test('an unloaded link delivers fixed-rate media without fictitious congestion', () => {
  for (const mode of ['fifo', 'fair', 'priority']) {
    const result = simulate({ ...fast, mode, scenario: 'idle' });
    assert.equal(result.summary.meetingLossPct, 0);
    assert.equal(result.summary.probeLossPct, 0);
    assert.equal(result.summary.roommateThroughputMbps, 0);
    assert.ok(Math.abs(result.summary.meetingReceivedMbps - 2.5) < 0.003);
    assert.ok(result.summary.rttP95Ms >= 40.168 - 1e-6);
    assert.ok(result.summary.rttP95Ms < 43);
  }
});

test('congestion creates actual FIFO queue delay; fair scheduling protects sparse traffic', () => {
  const idle = simulate({ ...fast, mode: 'fifo', scenario: 'idle' });
  const fifo = simulate({ ...fast, mode: 'fifo' });
  const fair = simulate({ ...fast, mode: 'fair' });
  assert.ok(fifo.summary.rttP95Ms > idle.summary.rttP95Ms + 150);
  assert.ok(fair.summary.rttP95Ms < fifo.summary.rttP95Ms * 0.4);
  assert.ok(fair.summary.meetingLossPct <= fifo.summary.meetingLossPct);
  assert.ok(fair.directions.up.accounting.ecnMarks > 0);
  assert.ok(fair.directions.down.accounting.ecnMarks > 0);
  assert.ok(fair.summary.roommateThroughputMbps > 20);
});

test('priority remains bounded and every bulk flow progresses under media overload', () => {
  const result = simulate({ ...fast, mode: 'priority', scenario: 'upload', meetingUpMbps: 8 });
  assert.ok(result.summary.meetingLossPct > 0, 'offered load above link capacity must not magically succeed');
  assert.ok(result.summary.probeLossPct > 0, 'measurements may also be lost when selected-device traffic is overloaded');
  for (const flow of result.directions.up.perFlowThroughputMbps) assert.ok(flow.mbps > 0.2, `${flow.id} was starved`);
  assert.ok(result.directions.up.meetingReceivedMbps + result.directions.up.roommateThroughputMbps <= 5.003);
});

test('all modes conserve bytes and packets after draining even when UDP overloads', () => {
  for (const mode of ['fifo', 'fair', 'priority']) {
    const result = simulate({ ...fast, mode, meetingUpMbps: 8, meetingDownMbps: 25 });
    for (const direction of ['up', 'down']) {
      const accounting = result.directions[direction].accounting;
      for (const kind of ['meeting', 'roommate', 'probe']) {
        assert.equal(accounting.offeredBytes[kind], accounting.deliveredBytes[kind] + accounting.droppedBytes[kind]);
        assert.equal(accounting.offeredPackets[kind], accounting.deliveredPackets[kind] + accounting.droppedPackets[kind]);
      }
      assert.equal(accounting.transmittedBytes, sum(accounting.deliveredBytes));
      assert.equal(accounting.remainingQueuedBytes, 0);
      assert.ok(accounting.maxQueuedBytes <= accounting.queueLimitBytes);
      assert.ok(accounting.transmittedBytes <= accounting.capacityBytesIncludingDrain + 1e-4);
      const expectedBusy = accounting.transmittedBytes / (result.directions[direction].capacityMbps * 125);
      assert.ok(Math.abs(accounting.transmissionBusyMs - expectedBusy) < 1e-5);
    }
  }
});

test('identical seeds reproduce complete event traces; startup phase varies with seed', () => {
  const config = { durationSeconds: 5, warmupSeconds: 1, mode: 'fair', seed: 7 };
  const first = simulate(config);
  assert.deepEqual(first, simulate(config));
  const other = simulate({ ...config, seed: 8 });
  assert.notEqual(first.raw.meeting.up[0].sentMs, other.raw.meeting.up[0].sentMs);
  assert.notDeepEqual(first.raw.probes, other.raw.probes);
});

test('directional bottlenecks are shared by media and bulk, with no cross-direction bulk', () => {
  const upload = simulate({ ...fast, scenario: 'upload', mode: 'fifo' });
  const download = simulate({ ...fast, scenario: 'download', mode: 'fifo' });
  assert.ok(upload.directions.up.roommateThroughputMbps > 0);
  assert.equal(upload.directions.down.roommateThroughputMbps, 0);
  assert.ok(download.directions.down.roommateThroughputMbps > 0);
  assert.equal(download.directions.up.roommateThroughputMbps, 0);
  assert.ok(upload.directions.up.meetingQueueP95Ms > upload.directions.down.meetingQueueP95Ms + 50);
  assert.ok(download.directions.down.meetingQueueP95Ms > download.directions.up.meetingQueueP95Ms + 50);
});

test('reported media rate and loss are derived from raw packet records after warmup', () => {
  const result = simulate({ ...fast, mode: 'fifo' });
  const { warmupSeconds, durationSeconds } = result.config;
  for (const direction of ['up', 'down']) {
    const records = result.raw.meeting[direction];
    const sent = records.filter((packet) => packet.sentMs >= warmupSeconds * 1000 && packet.sentMs < durationSeconds * 1000);
    const received = records.filter((packet) => !packet.lost && packet.receivedMs >= warmupSeconds * 1000 && packet.receivedMs < durationSeconds * 1000);
    const actualMbps = received.reduce((bytes, packet) => bytes + packet.bytes, 0) * 8 / (durationSeconds - warmupSeconds) / 1e6;
    const actualLoss = sent.filter((packet) => packet.lost).length / sent.length * 100;
    assert.ok(Math.abs(result.directions[direction].meetingReceivedMbps - actualMbps) < 1e-6);
    assert.ok(Math.abs(result.directions[direction].meetingLossPct - actualLoss) < 1e-6);
  }
  const rtts = result.raw.probes.filter((probe) => !probe.lost && probe.sentMs >= 2000 && probe.sentMs < 12000).map((probe) => probe.rttMs);
  assert.ok(Math.abs(result.summary.rttP95Ms - percentile(rtts, 0.95)) < 1e-6);
});

test('serialized packets cannot arrive faster than each bottleneck capacity', () => {
  const result = simulate({ ...fast, mode: 'priority' });
  for (const direction of ['up', 'down']) {
    const link = result.directions[direction];
    assert.ok(link.meetingReceivedMbps + link.roommateThroughputMbps <= link.capacityMbps + 0.003);
    const packets = result.raw.meeting[direction].filter((packet) => !packet.lost);
    for (let index = 1; index < packets.length; index++) {
      const minimumSpacing = result.config.packetBytes / (link.capacityMbps * 125);
      assert.ok(packets[index].receivedMs - packets[index - 1].receivedMs >= minimumSpacing - 1e-7);
    }
  }
});

test('larger propagation delay is included in observed RTT', () => {
  const result = simulate({ ...fast, scenario: 'idle', baseRttMs: 120 });
  for (const probe of result.raw.probes.filter((probe) => !probe.lost)) assert.ok(probe.rttMs >= 120.168 - 1e-7);
  assert.ok(result.summary.rttP95Ms < 123);
});

test('sample bins hold measured byte counts rather than invented chart values', () => {
  const result = simulate({ durationSeconds: 2.3, warmupSeconds: 0.5, sampleIntervalMs: 500, scenario: 'idle' });
  assert.equal(result.samples.length, 5);
  assert.equal(result.samples.at(-1).timeMs, 2300);
  for (const sample of result.samples) {
    const seconds = (sample.timeMs - sample.intervalStartMs) / 1000;
    assert.ok(Math.abs(sample.meetingReceivedMbps - sample.raw.meetingReceivedBytes * 8 / seconds / 1e6) < 1e-6);
    assert.ok(Number.isFinite(sample.upQueueMs));
    assert.ok(Number.isFinite(sample.downQueueMs));
  }
});

test('input validation rejects unsafe sizes, NaN, numeric strings, and invalid modes', () => {
  for (const input of [null, [], 'config', { mode: 'cake' }, { scenario: 'wifi' }, { seed: -1 }, { seed: 1.2 },
    { upMbps: Infinity }, { downMbps: NaN }, { durationSeconds: 1000 }, { durationSeconds: 4, warmupSeconds: 4 },
    { roommateFlows: 0 }, { roommateFlows: 1.5 }, { packetBytes: 0 }, { queueMs: '200' }, { priorityWeight: 100 }]) {
    assert.throws(() => normalizeConfig(input));
  }
  assert.equal(normalizeConfig({ scenario: 'mixed' }).scenario, 'bidirectional');
  assert.equal(normalizeConfig({ durationSeconds: 180 }).durationSeconds, 180);
  assert.throws(() => normalizeConfig({ durationSeconds: 181 }));
});

test('absence of completed samples is represented honestly with null', () => {
  const result = simulate({ durationSeconds: 2, warmupSeconds: 1.9, baseRttMs: 500, queueMs: 1000, scenario: 'upload', upMbps: 0.5, meetingUpMbps: 10 });
  if (result.summary.completedProbes === 0) {
    assert.equal(result.summary.rttP95Ms, null);
    assert.equal(result.summary.rttMeanMs, null);
  }
  for (const sample of result.samples) if (!sample.raw.probeRttsMs.length) assert.equal(sample.rttMs, null);
});
