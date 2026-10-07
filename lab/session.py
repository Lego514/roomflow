#!/usr/bin/env python3
"""Persistent, timed CAKE meeting sessions for the isolated Linux lab only."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import netlab

SESSION = netlab.HERE / ".session-state.json"
LOCK = netlab.HERE / ".session.lock"
EVENTS = netlab.HERE / ".session-events.jsonl"


def read_session():
    if not SESSION.exists():
        return None
    if SESSION.is_symlink() or SESSION.stat().st_uid != 0 or SESSION.stat().st_mode & 0o022:
        raise netlab.LabError("Session state must be root-owned, private, and not a symlink")
    value = json.loads(SESSION.read_text(encoding="utf-8"))
    if value.get("baseline_mode") not in ("fifo", "sqm") or not isinstance(value.get("expires_at"), (float, int)):
        raise netlab.LabError("Session baseline/expiry is invalid; refusing unsafe restoration")
    return value


def write_session(value):
    if SESSION.is_symlink():
        raise netlab.LabError("Refusing symlink session state")
    temp = SESSION.with_suffix(".tmp")
    if temp.is_symlink():
        raise netlab.LabError("Refusing symlink temporary state")
    fd = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2)
    os.replace(temp, SESSION)


def record_event(action, value, error=None):
    if EVENTS.is_symlink():
        raise netlab.LabError("Refusing symlink event log")
    event = {"at": time.time(), "action": action, "session_id": value.get("id"),
             "baseline_mode": value.get("baseline_mode"), "expires_at": value.get("expires_at")}
    if error:
        event["error"] = str(error)
    fd = os.open(EVENTS, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


@contextlib.contextmanager
def session_lock():
    import fcntl
    if LOCK.is_symlink():
        raise netlab.LabError("Refusing symlink lock")
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def restore(state, value, reason):
    # On failure, retain the active record, so subsequent startup/status retries.
    try:
        restored = netlab.set_mode(state, value["baseline_mode"])
        netlab.verify_mode(state, value["baseline_mode"])
    except netlab.LabError as exc:
        record_event("restore-failed", value, exc)
        raise
    value.update({"active": False, "ended_at": time.time(), "end_reason": reason})
    write_session(value)
    record_event(reason, value)
    return {"session": value, "lab": restored}


def reconcile(state, value):
    if value and value.get("active") and time.time() >= value["expires_at"]:
        return restore(state, value, "expired")
    if value and value.get("active"):
        netlab.verify_mode(state, "meeting")
    return {"session": value, "lab": netlab.status(state)}


def start(state, seconds, watch=True):
    if not 1 <= seconds <= 7200:
        raise netlab.LabError("Session duration must be 1..7200 seconds")
    previous = read_session()
    reconcile(state, previous)
    previous = read_session()
    if previous and previous.get("active"):
        raise netlab.LabError("A session is already active; stop it before starting another")
    if state["mode"] not in ("fifo", "sqm"):
        raise netlab.LabError("Set baseline mode to fifo or sqm before starting a timed session")
    netlab.verify_mode(state, state["mode"])
    now = time.time()
    value = {"id": uuid.uuid4().hex, "active": True, "baseline_mode": state["mode"],
             "lab_token": state["token"], "started_at": now, "expires_at": now + seconds}
    # Persist intent before applying: a crash during apply can still restore baseline.
    write_session(value)
    record_event("intent", value)
    try:
        netlab.set_mode(state, "meeting")
        value.update({"started_at": time.time(), "expires_at": time.time() + seconds})
        write_session(value)
        record_event("started", value)
        if watch:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_watch", "--id", value["id"]],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except BaseException as exc:
        record_event("apply-failed", value, exc)
        with contextlib.suppress(netlab.LabError):
            restore(state, value, "apply-failed")
        raise
    return {"session": value, "lab": netlab.status(state)}


def watch(session_id):
    # Worker can restart: persisted wall clock expiry is always authoritative.
    while True:
        with session_lock():
            value = read_session()
            if not value or not value.get("active") or value["id"] != session_id:
                return {"ok": True, "worker": "finished"}
            state = netlab.load_state()
            if value.get("lab_token") != state["token"]:
                raise netlab.LabError("Lab was replaced; refusing to apply old session to a new topology")
            if time.time() >= value["expires_at"]:
                return restore(state, value, "expired")
        time.sleep(0.2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("--seconds", type=int, default=60)
    start_parser.add_argument("--no-watch", action="store_true", help=argparse.SUPPRESS)
    commands.add_parser("status")
    commands.add_parser("stop")
    watch_parser = commands.add_parser("_watch", help=argparse.SUPPRESS)
    watch_parser.add_argument("--id", required=True)
    args = parser.parse_args(argv)
    try:
        netlab.guard_linux()
        if args.command == "_watch":
            result = watch(args.id)
        else:
            with session_lock():
                state = netlab.load_state()
                value = read_session()
                if value and value.get("active") and value.get("lab_token") != state["token"]:
                    raise netlab.LabError("Session belongs to a different lab; refusing to alter this topology")
                if args.command == "start":
                    result = start(state, args.seconds, not args.no_watch)
                elif args.command == "stop":
                    result = restore(state, value, "stopped") if value and value.get("active") else reconcile(state, value)
                else:
                    result = reconcile(state, value)
        print(json.dumps(result, indent=2))
        return 0
    except (netlab.LabError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
