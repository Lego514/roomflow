#!/usr/bin/env python3
"""Isolated, real Linux traffic experiment. Requires root in a disposable VM.

No host routes, host forwarding flags, or host firewall rules are changed.
Results are kernel/iperf measurements, not the browser's numerical model.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
from pathlib import Path
import re
import random
import csv
import shutil
import signal
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
STATE = HERE / ".netlab-state.json"
NAMES = {role: "nc-lab-" + role for role in ("meeting", "roommate", "router", "delay", "server")}
LINKS = [
    ("meeting", "eth0", "10.77.1.2/24", "router", "mlan", "10.77.1.1/24"),
    ("roommate", "eth0", "10.77.2.2/24", "router", "rlan", "10.77.2.1/24"),
    ("router", "wan", "10.77.3.1/30", "delay", "torouter", "10.77.3.2/30"),
    ("delay", "toserver", "10.77.4.1/30", "server", "eth0", "10.77.4.2/30"),
]
SHAPERS = [("router", "wan", "up_mbps", "src_ip", "mlan"),
           ("delay", "torouter", "down_mbps", "dst_ip", None)]
MEETING_IP = "10.77.1.2"
SERVER_IP = "10.77.4.2"
MODES = ("fifo", "sqm", "meeting")
SCENARIOS = ("idle", "upload", "download", "both")


class LabError(RuntimeError):
    pass


def run(*args, check=True, timeout=20):
    try:
        p = subprocess.run([str(a) for a in args], text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LabError(f"Cannot execute {' '.join(map(str, args))}: {exc}") from exc
    if check and p.returncode:
        raise LabError(f"Command failed ({p.returncode}): {' '.join(map(str, args))}\n{p.stderr.strip()}")
    return p


def ns(role, *args, **kwargs):
    return run("ip", "netns", "exec", NAMES[role], *args, **kwargs)


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise LabError(f"Refusing symlink output: {path}")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_state(state):
    if STATE.is_symlink():
        raise LabError("Refusing symlink state file")
    temporary = STATE.with_suffix(".tmp")
    if temporary.is_symlink():
        raise LabError("Refusing symlink temporary state file")
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(temporary, STATE)


def load_state():
    if STATE.is_symlink() or not STATE.exists():
        raise LabError("Owned lab state not found. Run setup first; inspect any existing nc-lab-* namespaces manually.")
    stat = STATE.stat()
    if stat.st_uid != 0 or stat.st_mode & 0o022:
        raise LabError("State must be root-owned and not group/world writable")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if state.get("names") != NAMES or not re.fullmatch(r"[0-9a-f]{32}", state.get("token", "")):
        raise LabError("State ownership data is invalid")
    return state


def guard_linux():
    if sys.platform != "linux":
        raise LabError("This lab needs Linux kernel networking. Use a disposable Ubuntu/Alpine VM; Windows numerical simulation runs separately.")
    if os.geteuid() != 0:
        raise LabError("Run with sudo/root inside the disposable Linux VM")


def existing_names():
    return {line.split()[0] for line in run("ip", "netns", "list").stdout.splitlines() if line.strip()}


def assert_owned(state, allow_missing=False):
    existing = existing_names()
    for role in state["created"]:
        if NAMES[role] not in existing:
            if allow_missing:
                continue
            raise LabError(f"Owned namespace is missing: {NAMES[role]}")
        links = json.loads(run("ip", "-j", "-n", NAMES[role], "link", "show").stdout)
        expected = "netcare-lab:" + state["token"]
        if not links or any(link.get("ifalias") != expected for link in links):
            raise LabError(f"Ownership marker mismatch in {NAMES[role]}; refusing to change or delete it")


def prerequisite_check():
    guard_linux()
    required = ("ip", "tc", "iperf3", "ping", "ethtool", "python3", "ss")
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        raise LabError("Missing packages: " + ", ".join(missing) +
                       ". Ubuntu: apt install python3 iproute2 iperf3 iputils-ping ethtool. "
                       "Alpine: apk add python3 iproute2 iproute2-tc iperf3 iputils ethtool.")
    probe = "nc-probe-" + uuid.uuid4().hex[:10]
    run("ip", "netns", "add", probe)
    try:
        run("ip", "-n", probe, "link", "add", "p0", "type", "veth", "peer", "name", "p1")
        for iface in ("p0", "p1"):
            run("ip", "-n", probe, "link", "set", iface, "up")
        commands = shaping_commands("fifo", "p0", 5, "src_ip", "p1", 40)
        # tc replace cannot change an existing handle's qdisc kind (HTB -> CAKE).
        # Match set_mode's explicit root deletion between independent strategies.
        commands.append(["tc", "qdisc", "del", "dev", "p0", "root"])
        commands += shaping_commands("meeting", "p0", 5, "src_ip", "p1", 40)
        commands.append(["tc", "qdisc", "replace", "dev", "p1", "root", "netem", "delay", "20ms", "limit", "10000"])
        for command in commands:
            run("ip", "netns", "exec", probe, *command)
        run("ip", "netns", "exec", probe, "ethtool", "-K", "p0", "gso", "off", "gro", "off", "tso", "off")
        ping_help = run("ping", "-h", check=False).stderr + run("ping", "-h", check=False).stdout
        if "-D" not in ping_help:
            raise LabError("Install iputils ping: timestamp option -D is required (BusyBox ping is insufficient)")
    except LabError as exc:
        raise LabError(str(exc) + "\nKernel must support netns/veth, HTB, pfifo, netem, CAKE, flower and skbedit. "
                       "Use the VM's full iproute2 tc and a kernel with CONFIG_NET_SCH_CAKE; no silent fallback is used.") from exc
    finally:
        run("ip", "netns", "delete", probe, check=False)
    return {"ok": True, "kernel": os.uname().release,
            "iperf": run("iperf3", "--version").stdout.splitlines()[0],
            "features": ["netns", "veth", "htb", "pfifo", "cake", "netem", "flower", "skbedit"]}


def shaping_commands(mode, iface, mbps, address_key, indev, rtt_ms):
    """Pure command plan; every mode uses exactly the same configured wire rate."""
    if mode not in MODES or not 0.1 <= mbps <= 1000 or not 1 <= rtt_ms <= 1000:
        raise LabError("Invalid shaping mode, capacity or RTT")
    rate = f"{mbps:g}mbit"
    if mode == "fifo":
        # HTB performs shaping, with one FIFO child. Size is ~300 ms at this rate.
        packet_limit = max(20, math.ceil(mbps * 1_000_000 / 8 * 0.3 / 1500))
        return [
            ["tc", "qdisc", "replace", "dev", iface, "root", "handle", "1:", "htb", "default", "10"],
            ["tc", "class", "replace", "dev", iface, "parent", "1:", "classid", "1:10", "htb", "rate", rate,
             "ceil", rate, "burst", "16k", "cburst", "16k", "quantum", "1514"],
            ["tc", "qdisc", "replace", "dev", iface, "parent", "1:10", "handle", "10:", "pfifo", "limit", str(packet_limit)],
        ]
    commands = [["tc", "qdisc", "replace", "dev", iface, "root", "handle", "1:", "cake", "bandwidth", rate,
                 "besteffort" if mode == "sqm" else "diffserv4", "dual-srchost" if address_key == "src_ip" else "dual-dsthost",
                 "rtt", f"{rtt_ms:g}ms", "raw", "wash", "no-ack-filter"]]
    if mode == "meeting":
        # CAKE priority minor 4 -> Voice, minor 2 -> Best Effort in diffserv4.
        # The default override defeats forged DSCP. No global nft/iptables needed.
        selected = ["tc", "filter", "add", "dev", iface, "parent", "1:", "protocol", "ip", "pref", "10", "flower"]
        if indev:
            selected += ["indev", indev]
        selected += [address_key, MEETING_IP + "/32", "action", "skbedit", "priority", "1:4"]
        commands += [selected,
                     ["tc", "filter", "add", "dev", iface, "parent", "1:", "protocol", "ip", "pref", "20",
                      "u32", "match", "u32", "0", "0", "action", "skbedit", "priority", "1:2"]]
    return commands


def set_mode(state, mode):
    assert_owned(state)
    previous = state.get("mode", "sqm")
    if previous not in MODES:
        previous = "sqm"
    try:
        for role, iface, capacity, key, indev in SHAPERS:
            # Delete old root first, to reset statistics and old root filters.
            ns(role, "tc", "qdisc", "del", "dev", iface, "root", check=False)
            for command in shaping_commands(mode, iface, state[capacity], key, indev, state["rtt_ms"]):
                ns(role, *command)
        verify_mode(state, mode)
    except LabError as exc:
        failures = []
        for role, iface, capacity, key, indev in SHAPERS:
            try:
                ns(role, "tc", "qdisc", "del", "dev", iface, "root", check=False)
                for command in shaping_commands(previous, iface, state[capacity], key, indev, state["rtt_ms"]):
                    ns(role, *command)
            except LabError as rollback:
                failures.append(str(rollback))
        if not failures:
            try:
                verify_mode(state, previous)
            except LabError as rollback:
                failures.append(str(rollback))
        if failures:
            state["mode"] = "unknown"
            save_state(state)
        raise LabError(f"Mode apply failed; rollback to {previous}: " + ("FAILED " + "; ".join(failures) if failures else "completed") + f"\n{exc}") from exc
    state["mode"] = mode
    save_state(state)
    return status(state)


def verify_mode(state, mode):
    for role, iface, capacity, *_ in SHAPERS:
        qdiscs = json.loads(ns(role, "tc", "-j", "qdisc", "show", "dev", iface).stdout)
        root = next((q for q in qdiscs if q.get("root")), None)
        kind = "htb" if mode == "fifo" else "cake"
        if root is None or root.get("kind") != kind:
            raise LabError(f"Readback failed: {role}/{iface} expected {kind}")
        raw = ns(role, "tc", "qdisc", "show", "dev", iface).stdout
        rate_raw = ns(role, "tc", "class", "show", "dev", iface).stdout if mode == "fifo" else raw
        match = re.search(r"(?:rate|bandwidth) ([\d.]+)([KMG]?)bit", rate_raw, re.I)
        factors = {"": 1, "k": 1000, "m": 1000000, "g": 1000000000}
        if not match or abs(float(match[1]) * factors[match[2].lower()] - state[capacity] * 1_000_000) > state[capacity] * 10000:
            raise LabError(f"Readback failed: wrong rate on {role}/{iface}")
        if mode != "fifo" and (mode == "meeting" and "diffserv4" not in raw or mode == "sqm" and "besteffort" not in raw):
            raise LabError(f"Readback failed: wrong CAKE strategy on {role}/{iface}")
        if mode == "meeting":
            filters = ns(role, "tc", "filter", "show", "dev", iface, "parent", "1:").stdout
            if "1:4" not in filters or "1:2" not in filters or MEETING_IP not in filters:
                raise LabError(f"Readback failed: selected/default priority rules missing on {role}/{iface}")


def status(state):
    assert_owned(state)
    snapshots = {}
    for role, iface, *_ in SHAPERS:
        snapshots[f"{role}/{iface}"] = {
            "qdisc": ns(role, "tc", "-s", "qdisc", "show", "dev", iface).stdout,
            "filters": ns(role, "tc", "-s", "filter", "show", "dev", iface, "parent", "1:", check=False).stdout,
        }
    return {"mode": state["mode"], "up_mbps": state["up_mbps"], "down_mbps": state["down_mbps"],
            "rtt_ms": state["rtt_ms"], "snapshots": snapshots}


def setup(up_mbps, down_mbps, rtt_ms):
    prerequisite_check()
    if STATE.exists() or STATE.is_symlink() or existing_names() & set(NAMES.values()):
        raise LabError("Existing state/topology found. Refusing to overwrite. Run owned teardown or inspect conflicts manually.")
    state = {"version": 1, "token": uuid.uuid4().hex, "names": NAMES, "created": [],
             "up_mbps": up_mbps, "down_mbps": down_mbps, "rtt_ms": rtt_ms, "mode": "sqm"}
    marker = "netcare-lab:" + state["token"]
    save_state(state)
    try:
        for role, name in NAMES.items():
            run("ip", "netns", "add", name)
            run("ip", "-n", name, "link", "set", "lo", "alias", marker)
            state["created"].append(role)
            save_state(state)
            run("ip", "-n", name, "link", "set", "lo", "up")
        for a, ai, addr_a, b, bi, addr_b in LINKS:
            run("ip", "-n", NAMES[a], "link", "add", ai, "type", "veth", "peer", "name", bi, "netns", NAMES[b])
            for role, iface, address in ((a, ai, addr_a), (b, bi, addr_b)):
                run("ip", "-n", NAMES[role], "link", "set", iface, "alias", marker)
                run("ip", "-n", NAMES[role], "addr", "add", address, "dev", iface)
                run("ip", "-n", NAMES[role], "link", "set", iface, "up")
                ns(role, "ethtool", "-K", iface, "gso", "off", "gro", "off", "tso", "off")
        for role in ("router", "delay"):
            ns(role, "python3", "-c", 'from pathlib import Path; Path("/proc/sys/net/ipv4/ip_forward").write_text("1")')
        for role, gateway in (("meeting", "10.77.1.1"), ("roommate", "10.77.2.1"), ("server", "10.77.4.1")):
            run("ip", "-n", NAMES[role], "route", "add", "default", "via", gateway)
        run("ip", "-n", NAMES["router"], "route", "add", "10.77.4.0/30", "via", "10.77.3.2")
        for subnet in ("10.77.1.0/24", "10.77.2.0/24"):
            run("ip", "-n", NAMES["delay"], "route", "add", subnet, "via", "10.77.3.1")
        for role, iface in (("delay", "toserver"), ("server", "eth0")):
            ns(role, "tc", "qdisc", "replace", "dev", iface, "root", "netem", "delay", f"{rtt_ms / 2:g}ms", "limit", "10000")
        set_mode(state, "sqm")
        for role in ("meeting", "roommate"):
            ns(role, "ping", "-c", "3", "-W", "2", SERVER_IP)
    except BaseException:
        # Only delete namespaces created in this call with verified loopback markers.
        for role in reversed(state["created"]):
            info = run("ip", "-j", "-n", NAMES[role], "link", "show", "lo", check=False)
            if info.returncode == 0 and json.loads(info.stdout)[0].get("ifalias") == marker:
                run("ip", "netns", "delete", NAMES[role], check=False)
        if not existing_names() & set(NAMES.values()):
            STATE.unlink(missing_ok=True)
        raise
    return status(state)


def teardown(state):
    assert_owned(state, allow_missing=True)
    for role in state["created"]:
        if NAMES[role] in existing_names() and run("ip", "netns", "pids", NAMES[role]).stdout.strip():
            raise LabError(f"Processes still running in {NAMES[role]}; stop the owned test before teardown. No processes were killed.")
    for role in reversed(state["created"]):
        if NAMES[role] in existing_names():
            run("ip", "netns", "delete", NAMES[role])
    STATE.unlink()
    return {"ok": True, "deleted": state["created"]}


def ping_summary(raw, measurement_start):
    samples = []
    for line in raw.splitlines():
        match = re.search(r"\[([\d.]+)\].*time[=<]([\d.]+)\s*ms", line)
        if match and float(match[1]) >= measurement_start:
            samples.append(float(match[2]))
    loss = re.search(r"([\d.]+)% packet loss", raw)
    ordered = sorted(samples)
    return {"samples": len(samples), "mean_ms": sum(samples) / len(samples) if samples else None,
            "p95_ms": ordered[math.ceil(len(ordered) * 0.95) - 1] if ordered else None,
            "ping_loss_including_warmup_pct": float(loss[1]) if loss else None}


def cpu_snapshot():
    rows = {}
    for line in Path("/proc/stat").read_text().splitlines():
        if re.match(r"cpu\d* ", line):
            parts = line.split()
            counters = [int(n) for n in parts[1:]]
            # guest counters are already included in user/nice.
            rows[parts[0]] = (sum(counters[:8]), counters[3] + counters[4])
    return rows


def cpu_usage(before, after):
    return {cpu: round(100 * (1 - (after[cpu][1] - value[1]) / (after[cpu][0] - value[0])), 2)
            for cpu, value in before.items() if cpu in after and after[cpu][0] > value[0]}


def flow_specs(scenario):
    specs = [("meeting-up", "meeting", 5201, False, True), ("meeting-down", "meeting", 5202, True, True)]
    if scenario in ("upload", "both"):
        specs.append(("roommate-up", "roommate", 5211, False, False))
    if scenario in ("download", "both"):
        specs.append(("roommate-down", "roommate", 5212, True, False))
    return specs


def receive_summary(data, udp):
    end = data.get("end", {})
    summary = end.get("sum_received") or end.get("sum") or {}
    fields = ("bits_per_second", "jitter_ms", "lost_packets", "packets", "lost_percent", "seconds") if udp else ("bits_per_second", "bytes", "seconds")
    return {key: summary.get(key) for key in fields}


def experiment(state, mode, scenario, duration, warmup, output, bulk_tos=0):
    if scenario not in SCENARIOS or duration < 5 or duration > 300 or warmup < 1 or warmup > 20:
        raise LabError("Scenario/duration/warmup invalid (duration 5..300 s, warmup 1..20 s)")
    set_mode(state, mode)
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise LabError(f"Output is not empty; refusing to replace measurements: {output}")
    output.mkdir(parents=True, exist_ok=True)
    children, files, logs = [], [], {}
    specs = flow_specs(scenario)

    def spawn(label, role, command):
        out = (output / f"{label}.json" if "iperf3" in command else output / f"{label}.txt").open("w", encoding="utf-8")
        err = (output / f"{label}.stderr.txt").open("w", encoding="utf-8")
        files.extend([out, err])
        p = subprocess.Popen(["ip", "netns", "exec", NAMES[role], *command], stdout=out, stderr=err, start_new_session=True)
        children.append((label, p))
        logs[label] = out.name
        return p

    metadata = {"kind": "linux-kernel-measurement", "mode": mode, "scenario": scenario,
                "duration_seconds": duration, "warmup_seconds": warmup, "bulk_tos": bulk_tos,
                "up_mbps": state["up_mbps"], "down_mbps": state["down_mbps"], "base_rtt_ms": state["rtt_ms"],
                "udp_target_bps_each_direction": 600000, "udp_payload_bytes": 256,
                "kernel": os.uname().release, "note": "UDP surrogate, not WebRTC quality or a real Wi-Fi measurement"}
    save_json(output / "metadata.json", metadata)
    save_json(output / "tc-before.json", status(state))
    start_cpu = cpu_snapshot()
    try:
        for label, _, port, _, _ in specs:
            spawn(label + "-server", "server", ["iperf3", "-s", "-1", "-p", str(port), "-J"])
        deadline = time.monotonic() + 5
        while True:
            listeners = ns("server", "ss", "-lnt").stdout
            if all(re.search(rf":{port}\s", listeners) for _, _, port, _, _ in specs):
                break
            if time.monotonic() > deadline:
                raise LabError("iperf3 servers did not start; inspect *-server.stderr.txt")
            time.sleep(0.1)
        started_at = time.time()
        spawn("ping", "meeting", ["ping", "-n", "-D", "-i", "0.1", "-w", str(duration + warmup), SERVER_IP])
        clients = []
        for label, role, port, reverse, udp in specs:
            command = ["iperf3", "-c", SERVER_IP, "-p", str(port), "-t", str(duration), "-O", str(warmup), "-J", "--get-server-output"]
            if reverse:
                command.append("-R")
            command += ["-u", "-b", "600K", "-l", "256"] if udp else ["-P", "4", "-S", str(bulk_tos)]
            clients.append((label, spawn(label, role, command)))
        deadline = time.monotonic() + duration + warmup + 30
        for label, child in children:
            child.wait(timeout=max(1, deadline - time.monotonic()))
            # Ping's exit 1 can legitimately indicate total packet loss.
            if child.returncode and label != "ping":
                raise LabError(f"{label} exited {child.returncode}; inspect raw/stderr in {output}")
    except subprocess.TimeoutExpired as exc:
        raise LabError(f"Traffic test timed out; partial raw data retained in {output}") from exc
    finally:
        for _, child in children:
            if child.poll() is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGTERM)
        for _, child in children:
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        for file in files:
            file.close()
    metadata["started_at_unix"] = started_at
    metadata["measurement_start_unix"] = started_at + warmup
    save_json(output / "metadata.json", metadata)
    flows = {}
    for label, _, _, reverse, udp in specs:
        client = json.loads(Path(logs[label]).read_text())
        server = json.loads(Path(logs[label + "-server"]).read_text())
        if client.get("error") or server.get("error"):
            raise LabError(f"iperf3 reported error in {label}; raw files retained")
        flows[label] = receive_summary(client if reverse else server, udp)
    cpu = cpu_usage(start_cpu, cpu_snapshot())
    summary = {**metadata, "rtt": ping_summary(Path(logs["ping"]).read_text(), started_at + warmup), "flows": flows,
               "cpu_busy_percent": cpu, "cpu_warning": any(value > 85 for key, value in cpu.items() if key != "cpu")}
    save_json(output / "tc-after.json", status(state))
    save_json(output / "summary.json", summary)
    return summary


def selftest(state, output, duration):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise LabError("Selftest output must be new/empty")
    output.mkdir(parents=True, exist_ok=True)
    report = {"kind": "linux-lab-selftest", "checks": [], "passed": False}
    try:
        for mode in MODES:
            for scenario in SCENARIOS:
                result = experiment(state, mode, scenario, duration, 2, output / f"{mode}-{scenario}", bulk_tos=192 if mode == "meeting" else 0)
                if result["rtt"]["samples"] < duration * 3:
                    raise LabError(f"Too few RTT samples in {mode}/{scenario}")
                for label, flow in result["flows"].items():
                    if not flow.get("bits_per_second"):
                        raise LabError(f"No measured receiver throughput for {mode}/{scenario}/{label}")
                if result["cpu_warning"]:
                    report["checks"].append({"name": f"{mode}-{scenario}-cpu", "warning": "A CPU averaged >85%; inspect VM bottleneck"})
                if mode == "meeting" and scenario == "both":
                    snapshots = json.loads((output / f"{mode}-{scenario}" / "tc-after.json").read_text())["snapshots"]
                    for link, snapshot in snapshots.items():
                        counts = [int(n) for n in re.findall(r"Sent \d+ bytes (\d+) pkt", snapshot["filters"])]
                        if len(counts) < 2 or not all(n > 0 for n in counts):
                            raise LabError(f"Selected/default priority counters not both active on {link}")
                    report["checks"].append({"name": "untrusted-dscp", "ok": True,
                                             "evidence": "Roommate CS6 tagged TCP; selected and forced-Best-Effort action counters both active"})
                report["checks"].append({"name": f"{mode}-{scenario}", "ok": True})
        set_mode(state, "sqm")
        session_script = str(HERE / "session.py")
        # Independent worker restores actual qdiscs without any status request.
        run(sys.executable, session_script, "start", "--seconds", "1")
        restore_deadline = time.monotonic() + 10
        while load_state()["mode"] != "sqm" and time.monotonic() < restore_deadline:
            time.sleep(0.2)
        state = load_state()
        verify_mode(state, "sqm")
        report["checks"].append({"name": "timed-kernel-restore", "ok": True})
        # Emulate a stopped timer service, then a fresh process reconciles expiry.
        run(sys.executable, session_script, "start", "--seconds", "1", "--no-watch")
        time.sleep(1.2)
        reconciled = json.loads(run(sys.executable, session_script, "status").stdout)
        if reconciled["session"]["active"] or reconciled["session"]["end_reason"] != "expired":
            raise LabError("Expired session was not reconciled after timer service restart")
        state = load_state()
        verify_mode(state, "sqm")
        report["checks"].append({"name": "restart-expiry-reconciliation", "ok": True})
        run(sys.executable, session_script, "start", "--seconds", "30")
        stopped = json.loads(run(sys.executable, session_script, "stop").stdout)
        if stopped["session"]["active"] or stopped["session"]["end_reason"] != "stopped":
            raise LabError("Early stop did not restore baseline")
        state = load_state()
        verify_mode(state, "sqm")
        report["checks"].append({"name": "early-stop-kernel-restore", "ok": True})
        report["passed"] = True
        return report
    except BaseException as exc:
        report["error"] = str(exc)
        raise
    finally:
        save_json(output / "selftest.json", report)
        # Selftest never leaves a meeting policy enabled.
        with contextlib.suppress(LabError):
            set_mode(state, "sqm")


def batch(state, output, duration, repeats, seed=22756):
    if not 1 <= repeats <= 10:
        raise LabError("Batch repeats must be 1..10")
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise LabError("Batch output must be new/empty")
    output.mkdir(parents=True, exist_ok=True)
    jobs = [(repeat, mode, scenario) for repeat in range(1, repeats + 1) for mode in MODES for scenario in SCENARIOS]
    random.Random(seed).shuffle(jobs)
    summaries, flat = [], []
    manifest = {"kind": "linux-kernel-batch", "repeats": repeats, "random_seed": seed, "completed": False, "measurements": summaries}
    try:
        for repeat, mode, scenario in jobs:
            folder = f"r{repeat}-{mode}-{scenario}"
            result = experiment(state, mode, scenario, duration, 3, output / folder)
            summaries.append({"repeat": repeat, "path": folder, "summary": result})
            row = {"repeat": repeat, "mode": mode, "scenario": scenario,
                   "rtt_p95_ms": result["rtt"]["p95_ms"], "cpu_warning": result["cpu_warning"]}
            for label, flow in result["flows"].items():
                for metric, value in flow.items():
                    row[f"{label}_{metric}"] = value
            flat.append(row)
            save_json(output / "batch.json", manifest)
            print(f"Measured {len(summaries)}/{len(jobs)}: {folder}", file=sys.stderr, flush=True)
        manifest["completed"] = True
        fields = ["repeat", "mode", "scenario", "rtt_p95_ms", "cpu_warning"]
        fields += sorted(set().union(*(row.keys() for row in flat)) - set(fields))
        with (output / "measurements.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(flat)
        return manifest
    finally:
        save_json(output / "batch.json", manifest)
        with contextlib.suppress(LabError):
            set_mode(state, "sqm")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    setup_parser = commands.add_parser("setup")
    setup_parser.add_argument("--up-mbps", type=float, default=5)
    setup_parser.add_argument("--down-mbps", type=float, default=20)
    setup_parser.add_argument("--rtt-ms", type=float, default=40)
    commands.add_parser("status")
    commands.add_parser("teardown")
    mode_parser = commands.add_parser("mode")
    mode_parser.add_argument("--mode", choices=MODES, required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--mode", choices=MODES, required=True)
    run_parser.add_argument("--scenario", choices=SCENARIOS, default="both")
    run_parser.add_argument("--duration", type=int, default=15)
    run_parser.add_argument("--warmup", type=int, default=3)
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--bulk-tos", type=lambda value: int(value, 0), default=0)
    selftest_parser = commands.add_parser("selftest")
    selftest_parser.add_argument("--output", required=True)
    selftest_parser.add_argument("--duration", type=int, default=8)
    batch_parser = commands.add_parser("batch")
    batch_parser.add_argument("--output", required=True)
    batch_parser.add_argument("--duration", type=int, default=15)
    batch_parser.add_argument("--repeats", type=int, default=3)
    batch_parser.add_argument("--seed", type=int, default=22756, help="run-order shuffle seed")
    args = parser.parse_args(argv)
    try:
        guard_linux()
        if args.command == "check":
            result = prerequisite_check()
        elif args.command == "setup":
            # Validate before touching any namespaces.
            shaping_commands("sqm", "wan", args.up_mbps, "src_ip", "mlan", args.rtt_ms)
            shaping_commands("sqm", "wan", args.down_mbps, "dst_ip", None, args.rtt_ms)
            result = setup(args.up_mbps, args.down_mbps, args.rtt_ms)
        else:
            state = load_state()
            session_path = HERE / ".session-state.json"
            if args.command != "status" and session_path.exists():
                if session_path.is_symlink() or session_path.stat().st_uid != 0 or session_path.stat().st_mode & 0o022:
                    raise LabError("Unsafe session state; refusing lab mutation")
                session_value = json.loads(session_path.read_text(encoding="utf-8"))
                if session_value.get("active"):
                    raise LabError("A timed session is active. Run lab/session.py status/stop before experiments, mode changes or teardown.")
            if args.command == "teardown":
                result = teardown(state)
            elif args.command == "status":
                result = status(state)
            elif args.command == "mode":
                result = set_mode(state, args.mode)
            elif args.command == "selftest":
                result = selftest(state, args.output, args.duration)
            elif args.command == "batch":
                result = batch(state, args.output, args.duration, args.repeats, args.seed)
            else:
                if not 0 <= args.bulk_tos <= 255:
                    raise LabError("--bulk-tos must fit the IPv4 TOS byte (0..255)")
                result = experiment(state, args.mode, args.scenario, args.duration, args.warmup, args.output, args.bulk_tos)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (LabError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; child traffic processes stopped. Run owned teardown when finished.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
