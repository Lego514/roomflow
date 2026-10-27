#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { validateObservations } from '../src/observations.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sources = {};
const inputs = {};
function readData(key, relative, kind, required = true) {
  const file = path.join(root, relative);
  if (!fs.existsSync(file) && !required) return;
  const raw = fs.readFileSync(file, 'utf8');
  const data = validateObservations(JSON.parse(raw), kind);
  // Offline files always show recorded history, even if a saved drill/export
  // was freshly generated. There is no live collector behind a portable file.
  data.monitor = { ...data.monitor, status: 'historical' };
  sources[key] = data;
  inputs[relative] = createHash('sha256').update(raw).digest('hex');
}
readData('demo', 'docs/evidence/observations-demo.json', 'historical-demo');
for (const scenario of ['delay', 'loss', 'dns']) {
  readData(`drill-${scenario}`, `results/incident-drills/${scenario}.json`, 'lab-drill', false);
}
const safeJSON = value => JSON.stringify(value).replaceAll('<', '\\u003c').replaceAll('\u2028', '\\u2028').replaceAll('\u2029', '\\u2029');
const css = fs.readFileSync(path.join(root, 'public/monitor.css'), 'utf8');
const js = fs.readFileSync(path.join(root, 'public/monitor.js'), 'utf8');
let html = fs.readFileSync(path.join(root, 'public/monitor.html'), 'utf8');
for (const [relative, raw] of [['public/monitor.css', css], ['public/monitor.js', js], ['public/monitor.html', html]]) {
  inputs[relative] = createHash('sha256').update(raw).digest('hex');
}
const styleTag = '<link rel="stylesheet" href="/monitor.css">';
const scriptTag = '<script src="/monitor.js" defer></script>';
if (!html.includes(styleTag) || !html.includes(scriptTag)) throw new Error('Standalone monitor shell is missing its expected asset tags.');
html = html.replace(styleTag, () => `<style>${css}</style>`)
  // The portable observation file has no companion homepage.
  .replace('<a href="/" class="rf-wordmark">', '<a href="#observations" class="rf-wordmark">')
  .replace(scriptTag, () => `<script>window.ROOMFLOW_OFFLINE_SOURCES=${safeJSON(sources)};window.ROOMFLOW_OFFLINE_DATA=window.ROOMFLOW_OFFLINE_SOURCES.demo;</script>`)
  .replace('</body>', () => `<script>${js.replaceAll('</script', '<\\/script')}</script></body>`);
// Inline scripts ignore defer. Place the UI script after its mounting element.
if (/\b(?:src|href)=["']https?:/i.test(html) || /<script[^>]+src=/i.test(html) || /<link[^>]+stylesheet/i.test(html)) {
  throw new Error('Portable demo unexpectedly depends on external assets.');
}
const output = path.join(root, 'artifacts/demo/RoomFlow.html');
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, html, 'utf8');
const manifest = { schemaVersion: 1, artifact: 'RoomFlow.html', sourceKinds: Object.keys(sources),
  inputSHA256: inputs, outputSHA256: createHash('sha256').update(html).digest('hex'),
  includesLocalPrivateHistory: false, requiresNetwork: false,
  notes: ['Historical aggregates and isolated drill results remain separately labelled. Rebuild after updating monitor assets or evidence.'] };
fs.writeFileSync(path.join(root, 'artifacts/demo/manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({ output: 'artifacts/demo/RoomFlow.html', bytes: Buffer.byteLength(html), sources: Object.keys(sources) }));
