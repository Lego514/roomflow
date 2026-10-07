#!/usr/bin/env python3
"""Independently audit exported raw measurements; never imports netlab logic."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def close(a, b):
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


DIAGNOSTIC_NAMES = {
    "idle-start", "r1-fifo", "r1-sqm", "r1-meeting", "r2-sqm", "r2-meeting", "r2-fifo",
    "r3-meeting", "r3-fifo", "r3-sqm", "idle-end",
}


def audit(root, diagnostic=False):
    failures, observations, measurements, offsets, cpus = [], [], [], [], []
    flow_count = 0
    for path in sorted(root.glob("*/summary.json")):
        folder = path.parent
        summary = read(path)
        metadata = read(folder / "metadata.json")
        measurement = {"name": folder.name, "mode": summary["mode"], "scenario": summary["scenario"],
                       "p95_ms": summary["rtt"]["p95_ms"], "flows": summary["flows"]}
        measurements.append(measurement)
        if summary["kind"] != "linux-kernel-measurement" or summary["kernel"] != metadata["kernel"]:
            failures.append(f"{folder.name}: measurement provenance mismatch")
        if not math.isclose(metadata["measurement_start_unix"], metadata["started_at_unix"] + metadata["warmup_seconds"], rel_tol=0, abs_tol=0.000001):
            failures.append(f"{folder.name}: warmup timestamp boundary mismatch")
        if diagnostic:
            idle = folder.name in ("idle-start", "idle-end")
            expected_mode = "sqm" if idle else folder.name.split("-", 1)[-1]
            if summary["mode"] != expected_mode or summary["scenario"] != ("idle" if idle else "both"):
                failures.append(f"{folder.name}: diagnostic mode/scenario mismatch")
            if metadata["duration_seconds"] != (10 if idle else 15) or metadata["warmup_seconds"] != 3:
                failures.append(f"{folder.name}: diagnostic duration/warmup mismatch")
        raw_ping = (folder / "ping.txt").read_text(encoding="utf-8")
        selected = []
        for line in raw_ping.splitlines():
            timestamp = re.search(r"^\[([0-9.]+)\]", line)
            rtt = re.search(r"\btime[=<]([0-9.]+)\s*ms", line)
            if timestamp and rtt and float(timestamp[1]) >= metadata["measurement_start_unix"]:
                selected.append(float(rtt[1]))
        selected.sort()
        if len(selected) != summary["rtt"]["samples"]:
            failures.append(f"{folder.name}: RTT sample count differs from raw timestamp selection")
        if not selected or not close(selected[int(math.ceil(0.95 * len(selected))) - 1], summary["rtt"]["p95_ms"]):
            failures.append(f"{folder.name}: independently recomputed RTT p95 mismatch")
        if selected and not close(sum(selected) / len(selected), summary["rtt"]["mean_ms"]):
            failures.append(f"{folder.name}: independently recomputed RTT mean mismatch")
        for label, reported in summary["flows"].items():
            flow_count += 1
            client = read(folder / f"{label}.json")
            server = read(folder / f"{label}-server.json")
            # Select physical receiver independently from the requested direction.
            receiver = client if label.endswith("down") else server
            raw = receiver["end"]["sum_received"]
            if raw.get("sender") is not False:
                failures.append(f"{folder.name}/{label}: selected record is not a receiver")
            for key, value in reported.items():
                if not close(value, raw.get(key)):
                    failures.append(f"{folder.name}/{label}: {key} not copied from receiver sum_received")
            if not close(raw["bytes"] * 8 / raw["seconds"], reported["bits_per_second"]):
                failures.append(f"{folder.name}/{label}: throughput fails independent bytes/time equation")
            if receiver.get("error") or client.get("error") or server.get("error"):
                failures.append(f"{folder.name}/{label}: iperf raw error")
            for peer in client["start"]["connected"]:
                expected = "10.77.1.2" if label.startswith("meeting") else "10.77.2.2"
                if peer["local_host"] != expected or peer["remote_host"] != "10.77.4.2":
                    failures.append(f"{folder.name}/{label}: endpoint escapes intended topology")
            settings = receiver["start"]["test_start"]
            if settings["omit"] != metadata["warmup_seconds"] or settings["duration"] != metadata["duration_seconds"]:
                failures.append(f"{folder.name}/{label}: iperf omit/duration does not match metadata")
            client_settings = client["start"]["test_start"]
            if label.startswith("meeting"):
                if settings["protocol"] != "UDP" or settings["blksize"] != 256 or receiver["start"]["target_bitrate"] != 600000:
                    failures.append(f"{folder.name}/{label}: unexpected meeting surrogate workload")
            elif settings["protocol"] != "TCP" or settings["num_streams"] != 4 or client_settings["tos"] != metadata["bulk_tos"]:
                failures.append(f"{folder.name}/{label}: unexpected bulk workload or DSCP tag")
            intervals = [item["sum"] for item in receiver["intervals"]]
            omitted = [item for item in intervals if item.get("omitted")]
            measured = [item for item in intervals if not item.get("omitted")]
            if not omitted or not measured:
                failures.append(f"{folder.name}/{label}: omitted or measured intervals missing")
            interval_bytes = sum(item["bytes"] for item in measured)
            if interval_bytes != raw["bytes"]:
                observations.append({"kind": "interval_end_byte_delta", "name": folder.name, "flow": label,
                                     "interval_bytes": interval_bytes, "receiver_end_bytes": raw["bytes"],
                                     "delta": raw["bytes"] - interval_bytes})
            stamp = receiver["start"]["timestamp"]
            offsets.append(stamp.get("timemillisecs", stamp["timesecs"] * 1000) / 1000 - metadata["started_at_unix"])
            if label.startswith("meeting") and reported["packets"]:
                if not close(reported["lost_packets"] / reported["packets"] * 100, reported["lost_percent"]):
                    observations.append({"kind": "iperf_loss_denominator", "name": folder.name, "flow": label,
                                         "lost": reported["lost_packets"], "received_summary_packets": reported["packets"],
                                         "reported_loss_pct": reported["lost_percent"],
                                         "end_sum_packets": receiver["end"]["sum"]["packets"]})
            for raw_file in (folder / f"{label}.stderr.txt", folder / f"{label}-server.stderr.txt"):
                if raw_file.read_text().strip():
                    observations.append({"kind": "stderr", "name": str(raw_file), "text": raw_file.read_text()})
        cpus.extend(summary["cpu_busy_percent"].values())
        if summary["cpu_warning"]:
            observations.append({"kind": "cpu_warning", "name": folder.name})
        before, after = read(folder / "tc-before.json"), read(folder / "tc-after.json")
        if set(after["snapshots"]) != {"router/wan", "delay/torouter"}:
            failures.append(f"{folder.name}: missing paired shared shapers")
        if after["up_mbps"] != 5 or after["down_mbps"] != 20 or after["rtt_ms"] != 40:
            failures.append(f"{folder.name}: default selftest capacity/RTT parameters changed")
        if summary["mode"] in ("sqm", "meeting"):
            for link, snapshot in after["snapshots"].items():
                expected_rate = "5Mbit" if link == "router/wan" else "20Mbit"
                expected_policy = "besteffort" if summary["mode"] == "sqm" else "diffserv4"
                if f"bandwidth {expected_rate}" not in snapshot["qdisc"] or expected_policy not in snapshot["qdisc"]:
                    failures.append(f"{folder.name}/{link}: raw kernel rate/strategy mismatch")
        if summary["mode"] == "meeting" and summary["scenario"] == "both":
            for link, snapshot in after["snapshots"].items():
                counts = [int(value) for value in re.findall(r"Sent \d+ bytes (\d+) pkt", snapshot["filters"])]
                tin_match = re.search(r"^\s+pkts\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", snapshot["qdisc"], re.M)
                tins = list(map(int, tin_match.groups())) if tin_match else []
                if len(counts) != 2 or len(tins) != 4 or not all(counts):
                    failures.append(f"{folder.name}/{link}: missing classification/action counter evidence")
                elif tins[0] or tins[2] or tins[3] != counts[0] or tins[1] != counts[1]:
                    failures.append(f"{folder.name}/{link}: priority action counters do not match Voice/Best Effort tins")
                if link == "router/wan" and ("indev mlan" not in snapshot["filters"] or "src_ip 10.77.1.2" not in snapshot["filters"]):
                    failures.append(f"{folder.name}/{link}: source/ingress trust boundary missing")
                if link == "delay/torouter" and "dst_ip 10.77.1.2" not in snapshot["filters"]:
                    failures.append(f"{folder.name}/{link}: meeting destination policy missing")
    if diagnostic:
        directory_names = {path.name for path in root.iterdir() if path.is_dir()}
        if {item["name"] for item in measurements} != DIAGNOSTIC_NAMES or directory_names != DIAGNOSTIC_NAMES:
            failures.append("Diagnostic requires the exact eleven named folders from run-diagnostic.sh")
    else:
        expected = {(mode, scenario) for mode in ("fifo", "sqm", "meeting") for scenario in ("idle", "upload", "download", "both")}
        counts = Counter((item["mode"], item["scenario"]) for item in measurements)
        if set(counts) != expected or len(set(counts.values())) != 1:
            failures.append("A balanced full factorial set of three modes by four scenarios is required")
    return {"passed": not failures, "profile": "diagnostic" if diagnostic else "full-factorial",
            "measurements": len(measurements), "receiver_flows": flow_count,
            "failures": failures, "observations": observations, "data": measurements,
            "max_guest_cpu_busy_pct": max(cpus) if cpus else None,
            "receiver_start_offset_range_seconds": [min(offsets), max(offsets)] if offsets else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnostic", action="store_true", help="Require the exact eleven-run diagnostic sequence instead of the full factorial matrix")
    args = parser.parse_args()
    result = audit(args.input, diagnostic=args.diagnostic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "data"}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
