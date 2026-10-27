#!/usr/bin/env python3
"""Real, isolated packet faults and recovery evidence for the incident monitor.

Only this process's uniquely named Linux namespaces are changed. The host's
routes, DNS, forwarding and firewall are never changed. No Internet access is
used. The generated evidence is a lab observation, not a home-network diagnosis.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from homenet.stats import MAX_LOSS_PCT, MAX_P95_MS
SCENARIOS = ("delay", "loss", "dns")
LAYERS = ("gateway", "internet", "dns", "service")
CLIENT = "192.0.2.2"
GATEWAY = "192.0.2.1"
ROUTER_WAN = "198.51.100.1"
SERVER = "198.51.100.2"
TCP_PORT = 18080
SERVICE_PORT = 18081
DNS_PORT = 15353
ATTEMPTS = 2
TIMEOUT_SECONDS = 1.2


class DrillError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def run(*args, check=True, timeout=15):
    try:
        result = subprocess.run([str(arg) for arg in args], capture_output=True,
                                text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DrillError(f"Cannot execute {args[0]}: {exc}") from exc
    if check and result.returncode:
        raise DrillError(f"Command failed ({result.returncode}): {' '.join(map(str, args))}\n"
                         f"{result.stderr.strip()}")
    return result


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise DrillError(f"Refusing symlink output: {path}")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def invalidate_dashboard(output, scenario):
    path = Path(output) / f"{scenario}.json"
    if path.is_symlink():
        raise DrillError(f"Refusing symlink output: {path}")
    path.unlink(missing_ok=True)


def prerequisite_check():
    if sys.platform != "linux" or not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise DrillError("Requires root in Linux/WSL2: sudo python3 lab/incident_drill.py --scenario all")
    missing = [name for name in ("ip", "tc", "ping", "sysctl") if not shutil.which(name)]
    if missing:
        raise DrillError("Missing tools: " + ", ".join(missing) +
                         ". Ubuntu: apt install iproute2 iputils-ping procps")
    return {"kernel": os.uname().release, "python": sys.version.split()[0],
            "requiredTools": {name: shutil.which(name) for name in ("ip", "tc", "ping", "sysctl")}}


def existing_names():
    return {line.split()[0] for line in run("ip", "netns", "list").stdout.splitlines() if line.strip()}


def dns_query(identifier):
    # RFC 2606 .invalid, served only by the private synthetic responder.
    question = b"\x05drill\x07invalid\x00" + struct.pack("!HH", 1, 1)
    return struct.pack("!HHHHHH", identifier, 0x0100, 1, 0, 0, 0) + question


def dns_answer(query):
    if len(query) < 12:
        return None
    return (query[:2] + struct.pack("!HHHHH", 0x8180, 1, 1, 0, 0) + query[12:] +
            b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 30, 4) + socket.inet_aton(SERVER))


def valid_dns_answer(response, identifier):
    if len(response) < 12:
        return False
    actual_id, flags, questions, answers, _, _ = struct.unpack("!HHHHHH", response[:12])
    return (actual_id == identifier and bool(flags & 0x8000) and flags & 0x000F == 0 and questions == 1 and answers == 1
            and response == dns_answer(dns_query(identifier)))


def serve(mode_path, ready_path):
    """Private server worker; it exists only in the owned server namespace."""
    selector = selectors.DefaultSelector()
    sockets = []
    counters = {"dnsReceived": 0, "dnsReplied": 0, "dnsDeliberatelyDropped": 0,
                "tcpAccepted": 0, "httpAccepted": 0}
    stats_path = Path(mode_path).parent / "server-stats.json"
    def save_counters():
        temporary = stats_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({**counters, "at": utc_now()}), encoding="utf-8")
        os.replace(temporary, stats_path)
    try:
        for port in (TCP_PORT, SERVICE_PORT):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(sock)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((SERVER, port))
            sock.listen(32)
            sock.setblocking(False)
            selector.register(sock, selectors.EVENT_READ, port)
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sockets.append(udp)
        udp.bind((SERVER, DNS_PORT))
        udp.setblocking(False)
        selector.register(udp, selectors.EVENT_READ, DNS_PORT)
        save_counters()
        Path(ready_path).write_text("ready", encoding="ascii")
        while True:
            for key, _ in selector.select(timeout=0.25):
                if key.data == DNS_PORT:
                    query, address = key.fileobj.recvfrom(512)
                    counters["dnsReceived"] += 1
                    if Path(mode_path).read_text(encoding="ascii") != "dns-blackhole":
                        answer = dns_answer(query)
                        if answer:
                            key.fileobj.sendto(answer, address)
                            counters["dnsReplied"] += 1
                    else:
                        counters["dnsDeliberatelyDropped"] += 1
                    save_counters()
                else:
                    connection, _ = key.fileobj.accept()
                    counters["httpAccepted" if key.data == SERVICE_PORT else "tcpAccepted"] += 1
                    save_counters()
                    with connection:
                        connection.settimeout(TIMEOUT_SECONDS)
                        if key.data == SERVICE_PORT:
                            # Consume the request so close cannot reset unread client data.
                            try:
                                connection.recv(1024)
                                connection.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 22\r\n\r\nRoomFlow isolated lab\n")
                            except (OSError, TimeoutError):
                                pass
    finally:
        selector.close()
        for sock in sockets:
            sock.close()


def percentiles(values):
    if not values:
        return None, None
    ordered = sorted(values)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return round(median, 3), round(ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)], 3)


def layer_from_attempts(attempts, layer="internet"):
    successful = [entry["elapsedMs"] for entry in attempts if entry.get("ok")]
    failed = sum(not entry.get("ok") for entry in attempts)
    p50, p95 = percentiles(successful)
    flags = []
    if attempts and 100 * failed / len(attempts) > MAX_LOSS_PCT:
        flags.append("unsuccessful-probes")
    if p95 is not None and p95 > MAX_P95_MS[layer]:
        flags.append("high-p95")
    return {"p50Ms": p50, "p95Ms": p95, "attempts": len(attempts), "failed": failed,
            "failurePct": round(100 * failed / len(attempts), 3) if attempts else None,
            "status": ("degraded" if flags else "ok") if attempts else "unknown", "flags": flags,
            "complete": bool(attempts), "observedSeries": 1, "expectedSeries": 1}


def ping_attempts():
    result = run("ping", "-n", "-c", str(ATTEMPTS), "-i", "0.05", "-W", "1", GATEWAY, check=False)
    if result.returncode not in (0, 1):
        raise DrillError("ICMP probe could not execute: " + result.stderr.strip())
    replies = {int(seq): float(ms) for seq, ms in re.findall(r"icmp_seq=(\d+).*?time[=<]([\d.]+)\s*ms", result.stdout)}
    values = [{"ok": seq in replies, "elapsedMs": replies.get(seq),
               "error": None if seq in replies else "no-icmp-reply"} for seq in range(1, ATTEMPTS + 1)]
    return values, {"stdout": result.stdout, "stderr": result.stderr, "exitCode": result.returncode}


def socket_attempt(kind):
    start = time.monotonic()
    response_detail = None
    try:
        if kind == "dns":
            identifier = int.from_bytes(os.urandom(2), "big")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(TIMEOUT_SECONDS)
                sock.connect((SERVER, DNS_PORT))
                sock.send(dns_query(identifier))
                response = sock.recv(512)
                if not valid_dns_answer(response, identifier):
                    raise OSError("invalid DNS response")
                response_detail = {"transactionIdMatched": True, "rcode": 0, "answers": 1, "bytes": len(response)}
        else:
            with socket.create_connection((SERVER, TCP_PORT if kind == "internet" else SERVICE_PORT),
                                          timeout=TIMEOUT_SECONDS) as sock:
                if kind == "service":
                    sock.sendall(b"GET / HTTP/1.0\r\nHost: drill.invalid\r\n\r\n")
                    response = sock.recv(1024)
                    if not response.startswith(b"HTTP/1.0 200 OK"):
                        raise OSError("invalid synthetic HTTP response")
                    response_detail = {"httpStatus": 200, "bytes": len(response)}
        return {"ok": True, "elapsedMs": round((time.monotonic() - start) * 1000, 3),
                "error": None, "response": response_detail}
    except (OSError, TimeoutError) as exc:
        return {"ok": False, "elapsedMs": round((time.monotonic() - start) * 1000, 3),
                "error": "timeout" if isinstance(exc, TimeoutError) else str(exc)}


def measure():
    at = utc_now()
    start = time.monotonic()
    icmp, raw_ping = ping_attempts()
    raw = {"gateway": icmp}
    for name in ("internet", "dns", "service"):
        raw[name] = [socket_attempt(name) for _ in range(ATTEMPTS)]
    layers = {name: layer_from_attempts(raw[name], name) for name in LAYERS}
    sample = {"at": at, "status": "degraded" if any(layer["status"] == "degraded" for layer in layers.values()) else "ok",
              "layers": layers}
    return {"sample": sample, "attempts": raw, "icmp": raw_ping,
            "completedAt": utc_now(), "durationMs": round((time.monotonic() - start) * 1000, 3)}


class IsolatedLab:
    def __init__(self):
        self.token = uuid.uuid4().hex[:12]
        self.names = {role: f"rfdi-{self.token}-{short}" for role, short in (("client", "c"), ("router", "r"), ("server", "s"))}
        self.marker = "roomflow-incident-drill:" + self.token
        self.created = []
        self.server = None
        self.temporary = None
        self.cleanup_report = None

    def ns(self, role, *args, **kwargs):
        return run("ip", "netns", "exec", self.names[role], *args, **kwargs)

    def ip(self, role, *args, **kwargs):
        return run("ip", "-n", self.names[role], *args, **kwargs)

    def assert_owned(self, role):
        links = json.loads(self.ip(role, "-j", "link", "show").stdout)
        if not links or any(link.get("ifalias") != self.marker for link in links):
            raise DrillError(f"Namespace ownership marker changed: {self.names[role]}; refusing mutation/deletion")

    def setup(self):
        if set(self.names.values()) & existing_names():
            raise DrillError("Unique namespace name already exists; refusing to touch it")
        for role in self.names:
            run("ip", "netns", "add", self.names[role])
            self.created.append(role)
            self.ip(role, "link", "set", "lo", "alias", self.marker)
            self.ip(role, "link", "set", "lo", "up")
        for left, left_if, left_ip, right, right_if, right_ip in (
            ("client", "eth0", CLIENT + "/30", "router", "lan", GATEWAY + "/30"),
            ("router", "wan", ROUTER_WAN + "/30", "server", "eth0", SERVER + "/30"),
        ):
            self.ip(left, "link", "add", left_if, "type", "veth", "peer", "name", right_if, "netns", self.names[right])
            for role, iface, address in ((left, left_if, left_ip), (right, right_if, right_ip)):
                self.ip(role, "link", "set", iface, "alias", self.marker)
                self.ip(role, "addr", "add", address, "dev", iface)
                self.ip(role, "link", "set", iface, "up")
        self.ip("client", "route", "add", "default", "via", GATEWAY)
        self.ip("server", "route", "add", "192.0.2.0/30", "via", ROUTER_WAN)
        self.ns("router", "sysctl", "-qw", "net.ipv4.ip_forward=1")
        for role in self.created:
            self.assert_owned(role)
        # A real netem operation checks kernel capability before any measurements.
        self.ns("router", "tc", "qdisc", "replace", "dev", "wan", "root", "netem", "delay", "1ms")
        self.ns("router", "tc", "qdisc", "del", "dev", "wan", "root")
        self.temporary = tempfile.TemporaryDirectory(prefix="roomflow-incident-")
        self.mode_path = Path(self.temporary.name) / "mode"
        self.ready_path = Path(self.temporary.name) / "ready"
        self.mode_path.write_text("normal", encoding="ascii")
        self.server = subprocess.Popen(["ip", "netns", "exec", self.names["server"], sys.executable,
                                        str(Path(__file__).resolve()), "--_serve", str(self.mode_path), str(self.ready_path)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 4
        while not self.ready_path.exists():
            if self.server.poll() is not None:
                raise DrillError("Synthetic server exited: " + self.server.communicate()[1])
            if time.monotonic() > deadline:
                raise DrillError("Synthetic server readiness timed out")
            time.sleep(0.02)
        return {"namespaces": self.names, "ownershipMarker": self.marker,
                "links": [f"client {CLIENT}/30 <-> {GATEWAY}/30 router", f"router {ROUTER_WAN}/30 <-> {SERVER}/30 server"],
                "routes": {role: self.ip(role, "-j", "route", "show").stdout for role in self.names},
                "routerForwarding": self.ns("router", "sysctl", "-n", "net.ipv4.ip_forward").stdout.strip(),
                "probes": {"gateway": f"ICMP {GATEWAY}", "internet": f"TCP {SERVER}:{TCP_PORT}",
                           "dns": f"UDP {SERVER}:{DNS_PORT} drill.invalid A", "service": f"HTTP {SERVER}:{SERVICE_PORT}"}}

    def inject(self, scenario):
        self.assert_owned("router")
        applied_at = utc_now()
        if scenario == "delay":
            self.ns("router", "tc", "qdisc", "replace", "dev", "wan", "root", "netem", "delay", "350ms")
        elif scenario == "loss":
            # 100% is deliberate: no random seed or probabilistic false pass.
            self.ns("router", "tc", "qdisc", "replace", "dev", "wan", "root", "netem", "loss", "100%")
        elif scenario == "dns":
            self.mode_path.write_text("dns-blackhole", encoding="ascii")
        else:
            raise DrillError("Unknown scenario")
        return {"at": applied_at, "scenario": scenario,
                "configured": {"delay": "router/wan egress netem delay 350ms", "loss": "router/wan egress netem loss 100%",
                               "dns": "live synthetic UDP responder receives requests but deliberately sends no replies"}[scenario],
                "qdiscReadback": self.ns("router", "tc", "-s", "qdisc", "show", "dev", "wan").stdout,
                "dnsResponderMode": self.mode_path.read_text(encoding="ascii")}

    def restore(self):
        self.assert_owned("router")
        self.mode_path.write_text("normal", encoding="ascii")
        result = self.ns("router", "tc", "qdisc", "del", "dev", "wan", "root", check=False)
        # No qdisc existed in the DNS scenario; all other failures are checked by readback.
        qdisc = self.ns("router", "tc", "qdisc", "show", "dev", "wan").stdout
        if "netem" in qdisc:
            raise DrillError("Injected netem remained after restoration")
        return {"at": utc_now(), "qdiscReadback": qdisc, "deleteExitCode": result.returncode,
                "dnsResponderMode": self.mode_path.read_text(encoding="ascii")}

    def measurement(self):
        value = self.ns("client", sys.executable, str(Path(__file__).resolve()), "--_measure", timeout=20)
        result = json.loads(value.stdout)
        result["serverReadback"] = self.server_stats()
        return result

    def server_stats(self):
        if self.temporary is None:
            return None
        path = Path(self.temporary.name) / "server-stats.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def cleanup(self):
        errors = []
        if self.server is not None and self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                self.server.kill()
                self.server.communicate(timeout=3)
        for role in reversed(self.created):
            try:
                if self.names[role] in existing_names():
                    # During partially failed setup a peer may lack an alias; only
                    # the lo marker is required for deletion of our known creation.
                    links = json.loads(self.ip(role, "-j", "link", "show").stdout)
                    lo = next((link for link in links if link["ifname"] == "lo"), None)
                    if lo is None or lo.get("ifalias") != self.marker:
                        raise DrillError("Ownership marker missing; refusing to delete " + self.names[role])
                    run("ip", "netns", "delete", self.names[role])
            except DrillError as exc:
                errors.append(str(exc))
        if self.temporary is not None:
            self.temporary.cleanup()
        remaining = sorted(set(self.names.values()) & existing_names())
        self.cleanup_report = {"verifiedAt": utc_now(), "namespacesAbsent": not remaining,
                               "remainingOwnedNames": remaining, "errors": errors}
        return self.cleanup_report


def audit_measurements(scenario, evidence):
    """Assert observed protocol behavior independently of configured injection truth."""
    records = evidence["measurements"]
    if [entry["phase"] for entry in records] != ["baseline"] * 2 + ["fault"] * 3 + ["recovery"] * 2:
        raise DrillError("Expected two baseline, three fault and two recovery samples")
    for entry in records:
        sample = entry["sample"]
        if entry["phase"] != "fault":
            if sample["status"] != "ok" or any(layer["status"] != "ok" for layer in sample["layers"].values()):
                raise DrillError("Baseline/recovery did not measure healthy complete probes")
        else:
            if sample["layers"]["gateway"]["status"] != "ok":
                raise DrillError("External fault unexpectedly affected gateway observations")
            affected = ("dns",) if scenario == "dns" else ("internet", "dns", "service")
            if any(sample["layers"][name]["status"] != "degraded" for name in affected):
                raise DrillError("Injected fault was not observed by every expected probe")
            if scenario == "delay" and any(sample["layers"][name]["failed"] or
                                            sample["layers"][name]["p95Ms"] <= MAX_P95_MS[name] for name in affected):
                raise DrillError("Delay must be measured as successful high-latency responses")
            if scenario in ("loss", "dns") and any(sample["layers"][name]["failurePct"] != 100 for name in affected):
                raise DrillError("Blackhole must measure all expected probes timing out")
            if scenario == "dns" and any(sample["layers"][name]["status"] != "ok" for name in ("internet", "service")):
                raise DrillError("DNS-only blackhole unexpectedly affected direct-IP TCP/HTTP")
    if not evidence["cleanup"]["namespacesAbsent"] or evidence["cleanup"]["errors"]:
        raise DrillError("Namespace cleanup did not verify clean")
    if "serverFinal" in evidence and evidence["serverFinal"] is None:
        raise DrillError("Synthetic responder counters were not captured")
    if scenario == "dns" and evidence.get("serverFinal"):
        if (evidence["serverFinal"]["dnsDeliberatelyDropped"] != 3 * ATTEMPTS or
                evidence["serverFinal"]["dnsReceived"] != 7 * ATTEMPTS or
                evidence["serverFinal"]["dnsReplied"] != 4 * ATTEMPTS):
            raise DrillError("Live DNS responder counters do not confirm receipt and deliberate silence")
    return {"passed": True, "sampleCount": len(records), "baselineSamples": 2, "faultSamples": 3,
            "recoverySamples": 2, "measurementAssertions": "gateway healthy, expected protocol fault observed, complete recovery, namespaces removed"}


def audit_incidents(scenario, samples, payload):
    from homenet.incidents import replay
    for count in (3, 4):
        if replay(samples[:count])["incidents"]:
            raise DrillError("Incident opened before three consecutive abnormal samples")
    for count in (5, 6):
        partial = replay(samples[:count])
        if len(partial["incidents"]) != 1 or partial["incidents"][0]["status"] != "open":
            raise DrillError("Incident must stay open until two complete recovery samples")
        if [event["type"] for event in partial["notifications"]] != ["opened"]:
            raise DrillError("An active incident emitted duplicate open notifications")
    incidents = payload["incidents"]
    if len(incidents) != 1 or incidents[0]["status"] != "resolved":
        raise DrillError("Expected exactly one resolved incident")
    expected_affected = ["dns"] if scenario == "dns" else ["dns", "internet", "service"]
    if incidents[0]["affectedLayers"] != expected_affected:
        raise DrillError("Incident affected layers do not match measured fault")
    if [event["type"] for event in payload["notifications"]] != ["opened", "resolved"]:
        raise DrillError("Expected exactly one open and one recovery notification")
    if incidents[0]["startedAt"] != samples[2]["at"] or incidents[0]["resolvedAt"] != samples[6]["at"]:
        # Backend canonicalizes fractional timestamp precision.
        from homenet.incidents import instant
        if (instant(incidents[0]["startedAt"]) != instant(samples[2]["at"]) or
                instant(incidents[0]["resolvedAt"]) != instant(samples[6]["at"])):
            raise DrillError("Incident start/recovery does not match observed samples")
    if incidents[0]["durationSeconds"] <= 0:
        raise DrillError("Incident must retain a positive observed duration")
    return "three abnormal checks open once; two healthy checks resolve once; start, duration and affected layers verified"


def drill(scenario, output):
    environment = prerequisite_check()
    lab = IsolatedLab()
    evidence = {"schemaVersion": 1, "source": "real-linux-packets", "scenario": scenario,
                "startedAt": utc_now(), "environment": environment, "measurements": [],
                "limits": ["Synthetic isolated IPv4 lab; no real ISP, home router, Wi-Fi or public service was tested.",
                           "Configured injection is ground truth only inside this lab; measured flags do not establish real-world root cause.",
                           "External and service labels are synthetic TCP/HTTP endpoints, not Internet or meeting-media quality.",
                           "100% loss is a deterministic total-loss case; partial loss and jitter are not covered."]}
    failure = None
    try:
        evidence["topology"] = lab.setup()
        for phase, count in (("baseline", 2), ("fault", 3), ("recovery", 2)):
            if phase == "fault":
                evidence["injection"] = lab.inject(scenario)
            elif phase == "recovery":
                evidence["restoration"] = lab.restore()
            for _ in range(count):
                measurement = lab.measurement()
                measurement["phase"] = phase  # phase is truth, never used to compute flags
                evidence["measurements"].append(measurement)
    except BaseException as exc:
        failure = exc
        evidence["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            evidence["serverFinal"] = lab.server_stats()
        except (OSError, ValueError) as exc:
            evidence["serverFinal"] = None
            evidence["serverStatsError"] = str(exc)
        finally:
            evidence["cleanup"] = lab.cleanup()
        evidence["completedAt"] = utc_now()
        save_json(Path(output) / f"{scenario}-evidence.json", evidence)
    if failure is not None:
        invalidate_dashboard(output, scenario)
        raise failure
    try:
        evidence["validation"] = audit_measurements(scenario, evidence)
        from homenet.dashboard import build_dashboard
        from homenet.incidents import Policy
        samples = [entry["sample"] for entry in evidence["measurements"]]
        payload = build_dashboard(samples, source_kind="lab-drill", label=f"Isolated Linux {scenario} and recovery",
                                  evaluated_at=samples[-1]["at"], generated_at=utc_now(), notes=evidence["limits"],
                                  policy=Policy(expected_series={name: 1 for name in LAYERS}))
        evidence["validation"]["incidentAssertions"] = audit_incidents(scenario, samples, payload)
        payload["drill"] = {"scenario": scenario, "injectedTruth": evidence["injection"],
                            "rawEvidenceFile": f"{scenario}-evidence.json", "validation": evidence["validation"],
                            "cleanup": evidence["cleanup"]}
        save_json(Path(output) / f"{scenario}-evidence.json", evidence)
        save_json(Path(output) / f"{scenario}.json", payload)
    except BaseException as exc:
        invalidate_dashboard(output, scenario)
        evidence["validation"] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        save_json(Path(output) / f"{scenario}-evidence.json", evidence)
        raise
    return payload


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--_serve":
        serve(sys.argv[2], sys.argv[3])
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--_measure":
        print(json.dumps(measure()))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=(*SCENARIOS, "all"), default="all")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "incident-drills",
                        help="output directory for dashboard JSON and separate raw evidence")
    args = parser.parse_args()
    def interrupted(signum, _frame):
        raise DrillError(f"Interrupted by signal {signum}; running owned-namespace cleanup")
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    try:
        for scenario in SCENARIOS if args.scenario == "all" else (args.scenario,):
            print(f"Running actual isolated {scenario} drill...", flush=True)
            drill(scenario, args.output)
            print(f"PASS {scenario}: {args.output / (scenario + '.json')}", flush=True)
    except (DrillError, OSError, ValueError, ImportError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
