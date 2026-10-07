import net from 'node:net';
import fs from 'node:fs';
import { randomUUID } from 'node:crypto';
const args = process.argv.slice(2);
const command = args[0] ?? '';
const timeoutMs = Number(args[1] ?? 15000);
const raw = args[2] === 'raw';
const marker = `__RF_${randomUUID().replaceAll('-','')}__`;
let output = '', finished = false;
const client = net.createConnection({ host:'127.0.0.1',port:4546 });
const finish = code => { if (finished) return; finished = true; clearTimeout(timer); client.destroy(); console.log(output); process.exitCode = code; };
const timer = setTimeout(() => finish(raw ? 0 : 124), timeoutMs);
client.on('connect', () => {
  if (raw) client.write(`${command}\n`);
  else client.write(`${command}\nprintf '\\n${marker}%s\\n' "$?"\n`);
});
client.on('data', data => {
  const text = data.toString('utf8'); output += text;
  fs.appendFileSync('.runtime/serial.log',text);
  const result = new RegExp(`\\r?\\n${marker}(\\d+)\\r?\\n`).exec(output);
  if (result) finish(Number(result[1]));
});
client.on('error', error => { output += error.message; finish(1); });
