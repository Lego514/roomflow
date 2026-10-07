import fs from 'node:fs';
import path from 'node:path';

export class SessionError extends Error {
  constructor(message, status = 400) { super(message); this.status = status; }
}

export function atomicJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.tmp`;
  fs.writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  fs.renameSync(temp, file);
}

export class SessionController {
  constructor({ file, now = Date.now, apply = () => {}, read = null }) {
    this.file = file;
    this.now = now;
    this.apply = apply;
    this.read = read;
    this.state = { mode: 'normal', device: 'meeting', expiresAt: null, revision: 0 };
    if (fs.existsSync(file)) {
      const saved = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (!['normal', 'meeting'].includes(saved.mode) || !Number.isSafeInteger(saved.revision) || saved.revision < 0
          || saved.device !== 'meeting' || (saved.mode === 'meeting' && (!Number.isSafeInteger(saved.expiresAt) || saved.expiresAt <= 0))
          || (saved.mode === 'normal' && saved.expiresAt !== null)) {
        throw new Error('Invalid persisted session state; inspect the session file before restarting.');
      }
      this.state = saved;
    }
    // Reapply the persisted desired state after a restart; expired leases restore normal.
    if (this.state.mode === 'meeting' && this.state.expiresAt <= this.now()) {
      this.commit({ ...this.state, mode: 'normal', expiresAt: null, revision: this.state.revision + 1 });
    } else {
      this.apply(this.state.mode);
      this.verify(this.state.mode);
    }
  }

  verify(mode) {
    if (this.read && this.read() !== mode) throw new SessionError('Strategy readback did not match the requested mode.', 503);
  }

  commit(next) {
    const previous = this.state;
    try {
      this.apply(next.mode);
      this.verify(next.mode);
      atomicJson(this.file, next);
      this.state = next;
    } catch (error) {
      try { this.apply(previous.mode); this.verify(previous.mode); }
      catch (rollbackError) { throw new SessionError(`Apply failed and rollback requires attention: ${rollbackError.message}`, 503); }
      throw new SessionError(`Strategy could not be applied: ${error.message}`, 503);
    }
    return { ...this.state };
  }

  status() {
    if (this.state.mode === 'meeting' && this.state.expiresAt <= this.now()) this.stop();
    this.verify(this.state.mode);
    return { ...this.state };
  }

  start({ durationSeconds, device }) {
    this.status();
    if (device !== 'meeting') throw new SessionError('Only the meeting lab device can be selected.');
    if (!Number.isInteger(durationSeconds) || durationSeconds < 1 || durationSeconds > 7200) {
      throw new SessionError('Duration must be an integer between 1 and 7200 seconds.');
    }
    if (this.state.mode === 'meeting') throw new SessionError('A meeting session is already active; end it before starting another.', 409);
    return this.commit({ mode: 'meeting', device, expiresAt: this.now() + durationSeconds * 1000, revision: this.state.revision + 1 });
  }

  stop() {
    if (this.state.mode === 'normal') { this.verify('normal'); return { ...this.state }; }
    return this.commit({ ...this.state, mode: 'normal', expiresAt: null, revision: this.state.revision + 1 });
  }
}
