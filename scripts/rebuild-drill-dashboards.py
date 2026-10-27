#!/usr/bin/env python3
"""Rebuild presentation/replay JSON from saved, previously executed packet drills.

This command performs no probes, subprocesses, namespace operations, or network
configuration. It preserves the original packet evidence byte for byte.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homenet.dashboard import atomic_export, build_dashboard
from homenet.incidents import LAYERS, Policy
from lab.incident_drill import audit_incidents, audit_measurements


def rebuild(directory: Path, scenario: str) -> dict:
    evidence_file = directory / f"{scenario}-evidence.json"
    original = evidence_file.read_bytes()
    evidence = json.loads(original)
    if evidence.get("source") != "real-linux-packets" or evidence.get("scenario") != scenario:
        raise ValueError("Expected original real-packet evidence for this scenario.")
    validation = audit_measurements(scenario, evidence)
    if not evidence.get("cleanup", {}).get("namespacesAbsent") or evidence.get("error"):
        raise ValueError("An interrupted or uncleared drill cannot become a successful replay.")
    samples = [measurement["sample"] for measurement in evidence["measurements"]]
    notes = list(evidence["limits"]) + [
        "Presentation and replay were rebuilt from saved packet observations; no new packets were measured.",
        f"Original packet run ended at {evidence['completedAt']}.",
    ]
    payload = build_dashboard(samples, source_kind="lab-drill", label=f"Isolated Linux {scenario} and recovery",
                              evaluated_at=samples[-1]["at"],
                              generated_at=datetime.now(timezone.utc).isoformat(), notes=notes,
                              policy=Policy(expected_series={name: 1 for name in LAYERS}))
    validation["incidentAssertions"] = audit_incidents(scenario, samples, payload)
    payload["drill"] = {"scenario": scenario, "injectedTruth": evidence["injection"],
                        "rawEvidenceFile": evidence_file.name,
                        "rawEvidenceSHA256": hashlib.sha256(original).hexdigest(),
                        "packetRunCompletedAt": evidence["completedAt"],
                        "validation": validation, "cleanup": evidence["cleanup"]}
    atomic_export(payload, directory / f"{scenario}.json")
    assert evidence_file.read_bytes() == original, "Raw packet evidence must remain unchanged."
    return {"scenario": scenario, "samples": len(samples), "incidents": len(payload["incidents"]),
            "replayFrames": len(payload.get("replay", {}).get("frames", [])), "rawEvidenceUnchanged": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "results/incident-drills")
    parser.add_argument("--scenario", choices=("all", "delay", "loss", "dns"), default="all")
    args = parser.parse_args(argv)
    for scenario in ("delay", "loss", "dns") if args.scenario == "all" else (args.scenario,):
        print(json.dumps(rebuild(args.directory, scenario)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
