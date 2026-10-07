/**
 * Deterministic discrete-event teaching model, NOT Linux CAKE or a real TCP stack.
 * See docs/simulator.md for assumptions, measurement windows and limitations.
 */
export const DEFAULT_CONFIG = Object.freeze({
  mode: 'fifo', scenario: 'bidirectional', durationSeconds: 30, warmupSeconds: 5,
  seed: 42, downMbps: 20, upMbps: 5, baseRttMs: 40, queueMs: 200,
  roommateFlows: 4, meetingDownMbps: 1.5, meetingUpMbps: 1,
  packetBytes: 1200, sampleIntervalMs: 500, priorityWeight: 3, aqmTargetMs: 10,
});

const MODES = new Set(['fifo', 'fair', 'priority']);
const SCENARIOS = new Set(['idle', 'upload', 'download', 'bidirectional']);

export function normalizeConfig(input = {}) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new TypeError('config must be an object');
  const config = { ...DEFAULT_CONFIG };
  for (const key of Object.keys(DEFAULT_CONFIG)) if (Object.hasOwn(input, key)) config[key] = input[key];
  if (config.scenario === 'mixed') config.scenario = 'bidirectional';
  if (!MODES.has(config.mode)) throw new RangeError('mode must be fifo, fair, or priority');
  if (!SCENARIOS.has(config.scenario)) throw new RangeError('scenario must be idle, upload, download, or bidirectional');
  const ranges = {
    durationSeconds: [2, 180], warmupSeconds: [0, 179], seed: [0, 4294967295],
    downMbps: [0.5, 100], upMbps: [0.5, 100], baseRttMs: [1, 500], queueMs: [5, 1000],
    roommateFlows: [1, 8], meetingDownMbps: [0.01, 50], meetingUpMbps: [0.01, 50],
    packetBytes: [128, 1500], sampleIntervalMs: [100, 2000], priorityWeight: [1, 8], aqmTargetMs: [1, 100],
  };
  for (const [key, [min, max]] of Object.entries(ranges)) {
    if (typeof config[key] !== 'number' || !Number.isFinite(config[key]) || config[key] < min || config[key] > max) {
      throw new RangeError(`${key} must be a finite number from ${min} to ${max}`);
    }
  }
  for (const key of ['seed', 'roommateFlows', 'packetBytes']) {
    if (!Number.isInteger(config[key])) throw new RangeError(`${key} must be an integer`);
  }
  if (config.warmupSeconds >= config.durationSeconds) throw new RangeError('warmupSeconds must be less than durationSeconds');
  return config;
}

class EventHeap {
  values = [];
  sequence = 0;
  push(time, order, type, data) {
    const item = { time, order, type, data, sequence: this.sequence++ };
    const a = this.values;
    let i = a.length;
    a.push(item);
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (!EventHeap.less(item, a[p])) break;
      a[i] = a[p]; i = p;
    }
    a[i] = item;
  }
  static less(a, b) {
    return a.time < b.time || (a.time === b.time && (a.order < b.order || (a.order === b.order && a.sequence < b.sequence)));
  }
  pop() {
    const a = this.values;
    const first = a[0];
    const last = a.pop();
    if (a.length) {
      let i = 0;
      while (true) {
        let c = i * 2 + 1;
        if (c >= a.length) break;
        if (c + 1 < a.length && EventHeap.less(a[c + 1], a[c])) c++;
        if (!EventHeap.less(a[c], last)) break;
        a[i] = a[c]; i = c;
      }
      a[i] = last;
    }
    return first;
  }
  get length() { return this.values.length; }
}

class PacketQueue {
  items = [];
  head = 0;
  bytes = 0;
  lastFinish = 0;
  push(packet) { this.items.push(packet); this.bytes += packet.bytes; }
  peek() { return this.items[this.head]; }
  pop() {
    const packet = this.items[this.head++];
    this.bytes -= packet.bytes;
    if (this.head > 128 && this.head * 2 > this.items.length) { this.items = this.items.slice(this.head); this.head = 0; }
    return packet;
  }
  dropTail() { const packet = this.items.pop(); this.bytes -= packet.bytes; return packet; }
  get length() { return this.items.length - this.head; }
}

function randomSource(seed) {
  let state = seed >>> 0;
  return () => {
    state += 0x6D2B79F5;
    let t = state;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

const counts = () => ({ meeting: 0, roommate: 0, probe: 0 });
const total = (counter) => Object.values(counter).reduce((a, b) => a + b, 0);
const mean = (items) => items.length ? items.reduce((a, b) => a + b, 0) / items.length : null;
export function percentile(items, q) {
  if (!items.length) return null;
  const sorted = [...items].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(q * sorted.length) - 1)];
}
function rounded(number) { return number === null ? null : Math.round(number * 1e6) / 1e6; }

/** Returns reproducible raw records, timed samples, and measurement-window summaries. */
export function simulate(input = {}) {
  const config = normalizeConfig(input);
  const events = new EventHeap();
  const random = randomSource(config.seed);
  const endMs = config.durationSeconds * 1000;
  const warmupMs = config.warmupSeconds * 1000;
  const measuredSeconds = config.durationSeconds - config.warmupSeconds;
  const measured = (time) => time >= warmupMs && time < endMs;
  const raw = { probes: [], meeting: { up: [], down: [] } };
  let now = 0;
  let packetId = 0;
  let handledEvents = 0;
  const sampleCount = Math.ceil(endMs / config.sampleIntervalMs);
  const bins = Array.from({ length: sampleCount }, (_, index) => ({
    timeMs: Math.min((index + 1) * config.sampleIntervalMs, endMs),
    intervalStartMs: index * config.sampleIntervalMs,
    measured: index * config.sampleIntervalMs >= warmupMs,
    rtts: [], upQueueMs: 0, downQueueMs: 0,
    meetingSent: 0, meetingLost: 0, meetingReceived: 0, roommateReceived: 0,
    meetingUpReceived: 0, meetingDownReceived: 0, roommateUpReceived: 0, roommateDownReceived: 0,
  }));
  function binAt(time) { return time >= 0 && time < endMs ? bins[Math.floor(time / config.sampleIntervalMs)] : undefined; }

  class Link {
    constructor(direction) {
      this.direction = direction;
      this.mbps = direction === 'up' ? config.upMbps : config.downMbps;
      this.bytesPerMs = this.mbps * 125;
      // Queue budget is waiting bytes; the non-preemptible packet in service is separate.
      this.queueLimitBytes = Math.max(1500, this.bytesPerMs * config.queueMs);
      this.queues = new Map();
      this.queuedBytes = 0;
      this.busy = false;
      this.busyUntil = 0;
      this.virtualTime = 0;
      this.offeredBytes = counts(); this.deliveredBytes = counts(); this.droppedBytes = counts();
      this.offeredPackets = counts(); this.deliveredPackets = counts(); this.droppedPackets = counts();
      this.transmittedBytes = 0; this.transmissionBusyMs = 0;
      this.maxQueuedBytes = 0; this.ecnMarks = 0;
      this.tcpFlows = [];
      this.rawQueue = [];
    }
    queueFor(flowId) {
      const key = config.mode === 'fifo' ? 'fifo' : flowId;
      if (!this.queues.has(key)) this.queues.set(key, new PacketQueue());
      return this.queues.get(key);
    }
    enqueue(packet) {
      this.offeredBytes[packet.kind] += packet.bytes;
      this.offeredPackets[packet.kind]++;
      packet.enqueuedMs = now;
      const queue = this.queueFor(packet.flowId);
      const weight = config.mode === 'priority' && packet.flowId === 'meeting' ? config.priorityWeight : 1;
      packet.finishTag = Math.max(queue.lastFinish, this.virtualTime) + packet.bytes / weight;
      queue.lastFinish = packet.finishTag;
      queue.push(packet);
      this.queuedBytes += packet.bytes;
      while (this.queuedBytes > this.queueLimitBytes) {
        // FIFO tail-drops. Fair modes evict from the longest byte queue, protecting
        // sparse flows from a global buffer occupied by a single burst.
        let victimQueue = queue;
        if (config.mode !== 'fifo') {
          for (const candidate of this.queues.values()) if (candidate.bytes > victimQueue.bytes) victimQueue = candidate;
        }
        const victim = victimQueue.dropTail();
        this.queuedBytes -= victim.bytes;
        victimQueue.lastFinish = victimQueue.length ? victimQueue.items.at(-1).finishTag : this.virtualTime;
        this.drop(victim, 'queue-full');
      }
      this.maxQueuedBytes = Math.max(this.maxQueuedBytes, this.queuedBytes);
      if (!this.busy) this.startService();
    }
    drop(packet, reason) {
      this.droppedBytes[packet.kind] += packet.bytes;
      this.droppedPackets[packet.kind]++;
      if (packet.kind === 'roommate') {
        events.push(now + Math.max(100, config.baseRttMs * 2), 1, 'loss', { link: this, flow: packet.flow });
      } else if (packet.kind === 'meeting') {
        const record = { id: packet.id, sentMs: packet.sentMs, receivedMs: null, bytes: packet.bytes, queueDelayMs: null, lost: true, reason };
        raw.meeting[this.direction].push(record);
        const bin = binAt(packet.sentMs); if (bin) bin.meetingLost += packet.bytes;
      } else {
        raw.probes.push({ sentMs: packet.probeSentMs, receivedMs: null, rttMs: null, lost: true, direction: this.direction });
      }
    }
    startService() {
      if (!this.queuedBytes) { this.busy = false; return; }
      let selected;
      for (const queue of this.queues.values()) {
        if (!queue.length) continue;
        if (!selected || queue.peek().finishTag < selected.peek().finishTag) selected = queue;
        if (config.mode === 'fifo') break;
      }
      const packet = selected.pop();
      this.queuedBytes -= packet.bytes;
      this.virtualTime = Math.max(this.virtualTime, packet.finishTag);
      packet.queueDelayMs = now - packet.enqueuedMs;
      packet.marked = false;
      if (config.mode !== 'fifo' && packet.kind === 'roommate' && packet.queueDelayMs > config.aqmTargetMs && now - packet.flow.lastMarkMs >= config.baseRttMs) {
        // Simplified ECN-AQM: one congestion mark per flow per base RTT when
        // dequeue sojourn exceeds target. This is NOT CoDel's control law.
        packet.marked = true;
        packet.flow.lastMarkMs = now;
        this.ecnMarks++;
      }
      this.busy = true;
      const serviceMs = packet.bytes / this.bytesPerMs;
      this.busyUntil = now + serviceMs;
      this.transmissionBusyMs += serviceMs;
      events.push(this.busyUntil, 0, 'depart', { link: this, packet });
    }
    depart(packet) {
      this.transmittedBytes += packet.bytes;
      if (packet.kind === 'roommate') {
        events.push(now + config.baseRttMs, 1, 'ack', { link: this, flow: packet.flow, marked: packet.marked });
        events.push(now + config.baseRttMs / 2, 1, 'receive', { link: this, packet });
      } else if (packet.kind === 'probe' && this.direction === 'up') {
        events.push(now + config.baseRttMs / 2, 2, 'probe-return', { packet });
        // Forward probe bytes have already reached this link's receiver.
        this.deliveredBytes.probe += packet.bytes; this.deliveredPackets.probe++;
      } else {
        events.push(now + config.baseRttMs / 2, 1, 'receive', { link: this, packet });
      }
      this.busy = false;
      this.startService();
    }
    receive(packet) {
      this.deliveredBytes[packet.kind] += packet.bytes;
      this.deliveredPackets[packet.kind]++;
      const bin = binAt(now);
      if (packet.kind === 'meeting') {
        raw.meeting[this.direction].push({ id: packet.id, sentMs: packet.sentMs, receivedMs: now, bytes: packet.bytes, queueDelayMs: packet.queueDelayMs, lost: false });
        if (bin) {
          bin.meetingReceived += packet.bytes;
          bin[this.direction === 'up' ? 'meetingUpReceived' : 'meetingDownReceived'] += packet.bytes;
        }
      } else if (packet.kind === 'roommate') {
        if (bin) {
          bin.roommateReceived += packet.bytes;
          bin[this.direction === 'up' ? 'roommateUpReceived' : 'roommateDownReceived'] += packet.bytes;
        }
        if (measured(now)) packet.flow.measuredReceivedBytes += packet.bytes;
      } else {
        const rttMs = now - packet.probeSentMs;
        raw.probes.push({ sentMs: packet.probeSentMs, receivedMs: now, rttMs, lost: false });
        if (bin) bin.rtts.push(rttMs);
      }
    }
    queueDelayMs() { return this.queuedBytes / this.bytesPerMs + Math.max(0, this.busyUntil - now); }
  }

  const links = { up: new Link('up'), down: new Link('down') };
  function fillWindow(link, flow) {
    if (now >= endMs) return;
    while (flow.inFlight < Math.max(2, Math.floor(flow.cwnd))) {
      flow.inFlight++;
      link.enqueue({ id: packetId++, kind: 'roommate', flowId: flow.id, flow, bytes: 1500, sentMs: now });
    }
  }
  function reduceWindow(flow, factor) {
    if (now - flow.lastReductionMs >= config.baseRttMs) {
      flow.cwnd = Math.max(2, flow.cwnd * factor);
      flow.lastReductionMs = now;
    }
  }
  for (const direction of ['up', 'down']) {
    const link = links[direction];
    const meetingMbps = direction === 'up' ? config.meetingUpMbps : config.meetingDownMbps;
    const interval = config.packetBytes * 8 / (meetingMbps * 1000);
    const offset = random() * interval;
    for (let time = offset; time < endMs; time += interval) events.push(time, 2, 'meeting-send', { link });
    const loaded = config.scenario === 'bidirectional' || (direction === 'up' && config.scenario === 'upload') || (direction === 'down' && config.scenario === 'download');
    if (loaded) {
      for (let index = 0; index < config.roommateFlows; index++) {
        const flow = { id: `roommate-${index}`, cwnd: 10, inFlight: 0, lastReductionMs: -Infinity, lastMarkMs: -Infinity, measuredReceivedBytes: 0 };
        link.tcpFlows.push(flow);
        events.push(random() * 5, 2, 'tcp-start', { link, flow });
      }
    }
  }
  for (let time = random() * 100; time < endMs; time += 100) events.push(time, 2, 'probe-send', {});
  for (const bin of bins) events.push(bin.timeMs, 3, 'sample', { bin });

  while (events.length) {
    const event = events.pop();
    now = event.time;
    handledEvents++;
    const data = event.data;
    switch (event.type) {
      case 'meeting-send': {
        const packet = { id: packetId++, kind: 'meeting', flowId: 'meeting', bytes: config.packetBytes, sentMs: now };
        const bin = binAt(now); if (bin) bin.meetingSent += packet.bytes;
        data.link.enqueue(packet); break;
      }
      case 'tcp-start': fillWindow(data.link, data.flow); break;
      case 'depart': data.link.depart(data.packet); break;
      case 'receive': data.link.receive(data.packet); break;
      case 'ack':
        data.flow.inFlight--;
        if (data.marked) reduceWindow(data.flow, 0.75);
        else data.flow.cwnd = Math.min(1024, data.flow.cwnd + 1 / data.flow.cwnd);
        fillWindow(data.link, data.flow); break;
      case 'loss':
        data.flow.inFlight--;
        reduceWindow(data.flow, 0.7);
        fillWindow(data.link, data.flow); break;
      case 'probe-send':
        links.up.enqueue({ id: packetId++, kind: 'probe', flowId: 'meeting', bytes: 84, sentMs: now, probeSentMs: now }); break;
      case 'probe-return':
        links.down.enqueue({ id: packetId++, kind: 'probe', flowId: 'meeting', bytes: 84, sentMs: now, probeSentMs: data.packet.probeSentMs }); break;
      case 'sample':
        data.bin.upQueueMs = links.up.queueDelayMs(); data.bin.downQueueMs = links.down.queueDelayMs();
        links.up.rawQueue.push(data.bin.upQueueMs); links.down.rawQueue.push(data.bin.downQueueMs); break;
      default: throw new Error(`Unknown event ${event.type}`);
    }
  }

  const directionResults = {};
  for (const direction of ['up', 'down']) {
    const link = links[direction];
    const meeting = raw.meeting[direction].sort((a, b) => a.sentMs - b.sentMs);
    const sentWindow = meeting.filter((packet) => measured(packet.sentMs));
    const receivedWindow = meeting.filter((packet) => !packet.lost && measured(packet.receivedMs));
    const arrived = sentWindow.filter((packet) => !packet.lost);
    const variations = [];
    let rfc3550JitterMs = 0;
    for (let i = 1; i < arrived.length; i++) {
      const previousTransit = arrived[i - 1].receivedMs - arrived[i - 1].sentMs;
      const transit = arrived[i].receivedMs - arrived[i].sentMs;
      const variation = Math.abs(transit - previousTransit);
      variations.push(variation);
      rfc3550JitterMs += (variation - rfc3550JitterMs) / 16;
    }
    const meetingBytes = receivedWindow.reduce((sum, packet) => sum + packet.bytes, 0);
    const roommateBytes = link.tcpFlows.reduce((sum, flow) => sum + flow.measuredReceivedBytes, 0);
    directionResults[direction] = {
      capacityMbps: link.mbps,
      meetingReceivedMbps: rounded(meetingBytes * 8 / measuredSeconds / 1e6),
      roommateThroughputMbps: rounded(roommateBytes * 8 / measuredSeconds / 1e6),
      meetingLossPct: rounded(sentWindow.length ? sentWindow.filter((packet) => packet.lost).length / sentWindow.length * 100 : 0),
      meetingJitterMs: rounded(mean(variations) ?? 0),
      meetingJitterP95Ms: rounded(percentile(variations, 0.95) ?? 0),
      rfc3550JitterMs: rounded(rfc3550JitterMs),
      meetingQueueP95Ms: rounded(percentile(arrived.map((packet) => packet.queueDelayMs), 0.95)),
      meetingSentPackets: sentWindow.length,
      meetingLostPackets: sentWindow.filter((packet) => packet.lost).length,
      perFlowThroughputMbps: link.tcpFlows.map((flow) => ({ id: flow.id, mbps: rounded(flow.measuredReceivedBytes * 8 / measuredSeconds / 1e6) })),
      accounting: {
        offeredBytes: link.offeredBytes, deliveredBytes: link.deliveredBytes, droppedBytes: link.droppedBytes,
        offeredPackets: link.offeredPackets, deliveredPackets: link.deliveredPackets, droppedPackets: link.droppedPackets,
        transmittedBytes: link.transmittedBytes, transmissionBusyMs: link.transmissionBusyMs,
        elapsedMsIncludingDrain: now, capacityBytesIncludingDrain: now * link.bytesPerMs,
        remainingQueuedBytes: link.queuedBytes, queueLimitBytes: link.queueLimitBytes,
        maxQueuedBytes: link.maxQueuedBytes, ecnMarks: link.ecnMarks,
      },
    };
  }
  raw.probes.sort((a, b) => a.sentMs - b.sentMs);
  const probeWindow = raw.probes.filter((probe) => measured(probe.sentMs));
  const rtts = probeWindow.filter((probe) => !probe.lost).map((probe) => probe.rttMs);
  const up = directionResults.up; const down = directionResults.down;
  const meetingSent = up.meetingSentPackets + down.meetingSentPackets;
  const summary = {
    measurementSeconds: measuredSeconds,
    rttMeanMs: rounded(mean(rtts)), rttP50Ms: rounded(percentile(rtts, 0.5)), rttP95Ms: rounded(percentile(rtts, 0.95)),
    probeLossPct: rounded(probeWindow.length ? probeWindow.filter((probe) => probe.lost).length / probeWindow.length * 100 : 0),
    meetingJitterMs: rounded((up.meetingJitterMs * up.meetingSentPackets + down.meetingJitterMs * down.meetingSentPackets) / Math.max(1, meetingSent)),
    meetingLossPct: rounded((up.meetingLostPackets + down.meetingLostPackets) / Math.max(1, meetingSent) * 100),
    meetingReceivedMbps: rounded(up.meetingReceivedMbps + down.meetingReceivedMbps),
    roommateThroughputMbps: rounded(up.roommateThroughputMbps + down.roommateThroughputMbps),
    meetingUpMbps: up.meetingReceivedMbps, meetingDownMbps: down.meetingReceivedMbps,
    roommateUpMbps: up.roommateThroughputMbps, roommateDownMbps: down.roommateThroughputMbps,
    completedProbes: rtts.length,
  };
  const samples = bins.map((bin) => {
    const seconds = (bin.timeMs - bin.intervalStartMs) / 1000;
    return {
      timeMs: bin.timeMs, intervalStartMs: bin.intervalStartMs, measured: bin.measured,
      rttMs: rounded(mean(bin.rtts)), rttP95Ms: rounded(percentile(bin.rtts, 0.95)),
      meetingLossPct: rounded(bin.meetingSent ? bin.meetingLost / bin.meetingSent * 100 : 0),
      meetingReceivedMbps: rounded(bin.meetingReceived * 8 / seconds / 1e6),
      roommateThroughputMbps: rounded(bin.roommateReceived * 8 / seconds / 1e6),
      meetingUpMbps: rounded(bin.meetingUpReceived * 8 / seconds / 1e6), meetingDownMbps: rounded(bin.meetingDownReceived * 8 / seconds / 1e6),
      roommateUpMbps: rounded(bin.roommateUpReceived * 8 / seconds / 1e6), roommateDownMbps: rounded(bin.roommateDownReceived * 8 / seconds / 1e6),
      upQueueMs: rounded(bin.upQueueMs), downQueueMs: rounded(bin.downQueueMs),
      raw: { meetingSentBytes: bin.meetingSent, meetingLostBytes: bin.meetingLost, meetingReceivedBytes: bin.meetingReceived, roommateReceivedBytes: bin.roommateReceived, probeRttsMs: bin.rtts },
    };
  });
  return {
    config,
    model: {
      name: 'Discrete-event WFQ / ECN-AIMD teaching model', version: 1,
      realNetwork: false, linuxCake: false, handledEvents,
      throughputUnit: 'Mbps of modeled serialized packet bytes; up and down totals are summed',
      assumptions: ['Independent shared upload and download bottlenecks', 'Fixed-rate UDP media and congestion-controlled ACK-paced bulk flows', 'Fixed propagation delay; TCP ACKs use a delay model without reverse-link serialization', 'Weighted fair scheduling with simplified ECN-AQM; not Linux CAKE/CoDel', 'No radio, codec, application or ISP outage model'],
    },
    summary, samples, raw, directions: directionResults,
  };
}
