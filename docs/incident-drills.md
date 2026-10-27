# Isolated incident and recovery drills

`lab/incident_drill.py` sends real ICMP, TCP, HTTP and UDP DNS packets in a Linux
network namespace lab. It exercises the same `homenet.incidents` replay engine
and dashboard JSON contract as saved home observations. The UI can import the
resulting dashboard files for an offline walkthrough.

These are synthetic lab results. They do not diagnose the home connection,
establish an ISP fault, or demonstrate a repaired router or better call quality.

## Run

Use a disposable Ubuntu Linux machine or an existing WSL2 Ubuntu instance. The
lab needs root for namespace/veth/netem operations, Python 3 and the `ip`, `tc`,
`ping`, and `sysctl` commands. It does not need iperf, containers, an Internet
connection or a running RoomFlow server. Install missing Ubuntu tools only if
needed: `sudo apt install iproute2 iputils-ping procps`.

From the repository root:

```sh
sudo python3 lab/incident_drill.py --scenario all --output results/incident-drills
# A single case is also supported:
sudo python3 lab/incident_drill.py --scenario dns --output results/incident-drills
```

From PowerShell with an existing `Ubuntu-24.04` WSL distribution:

```powershell
wsl -d Ubuntu-24.04 -u root -- python3 '/mnt/c/dev/NETWORK APP/lab/incident_drill.py' --scenario all --output '/mnt/c/dev/NETWORK APP/results/incident-drills'
```

The actual kernel's namespace, veth and netem operations are checked during
setup. A missing permission or kernel feature fails the run; there is no
simulated fallback. Normal execution takes about a minute, depending on the host.

## Topology and isolation

```text
client                       router                         server
192.0.2.2/30 -- veth -- 192.0.2.1/30
                       198.51.100.1/30 -- veth -- 198.51.100.2/30
 ICMP gateway              impairment on wan egress          TCP :18080
                                                          HTTP :18081
                                                   synthetic DNS :15353
```

All addresses are RFC 5737 documentation ranges, and `drill.invalid` is a
synthetic DNS name. There is no link to a host interface or bridge. Only the
owned router namespace enables IPv4 forwarding. No host forwarding setting,
route, DNS file, firewall rule or home-router configuration is changed. Veth
pairs are created inside the owned namespaces and disappear with them.

Every run uses three unique `rfdi-<random-token>-{c,r,s}` namespace names and
labels its interfaces with an ownership marker. It refuses collisions or changed
ownership markers. The synthetic server process stops before namespace deletion.
Cleanup runs in `finally`, including ordinary errors, Ctrl+C and SIGTERM, then
reads `ip netns list` to verify that its three names are absent. SIGKILL or a
kernel/host crash cannot run Python cleanup; inspect the recorded namespace names
if execution is killed that way. It never deletes another run's namespace.

## Faults and pass conditions

Each scenario collects **two healthy samples, three affected samples and two
healthy recovery samples**. Each sample has two attempts per probe layer.
Thresholds come from `homenet.stats`, so measured flags match the monitor policy.
Successful latency percentiles exclude failed attempts; a timeout is retained
as a failed probe, and all-failed probes have null latency rather than zero.

| Scenario | Controlled injection | Required measured evidence |
| --- | --- | --- |
| `delay` | `netem delay 350ms` on the router's external egress | Healthy gateway; successful external TCP, DNS and HTTP responses above their latency thresholds |
| `loss` | `netem loss 100%` on the same egress | Healthy gateway; all external TCP, DNS and HTTP attempts fail |
| `dns` | A live synthetic UDP responder receives queries and sends no replies | Healthy gateway/direct-IP TCP/HTTP; every DNS attempt times out |

The loss case deliberately uses deterministic total loss. Partial loss, jitter,
IPv6, Wi-Fi, public resolvers, public services and real meeting-media traffic
are outside this lab's coverage. HTTP timing includes a request/response; TCP
timing measures connection establishment. Two successful attempts are sufficient
for this controlled smoke test and do not characterize tail latency in production.

After measurements, the runner asserts the observed protocol behavior without
using the phase or injection labels to calculate flags. It separately replays
the measurement prefixes and asserts:

1. One or two affected checks do not create an incident.
2. The third affected check opens exactly one incident and one local notification.
3. The first healthy check leaves it open without a second open notification.
4. The second complete healthy check resolves it with one recovery notification.
5. The saved incident has the measured start, positive observed duration and
   expected affected layers, and all owned namespaces have been removed.

## Evidence and offline display

For each scenario, the output directory receives two files:

- `<scenario>.json`: schema-version-1 dashboard payload containing the observed
  timeline, latest sample, resolved incident and two local transition records.
- `<scenario>-evidence.json`: environment, topology and routes; configured
  injection truth/readback; each measured attempt and its elapsed time/error;
  raw ICMP output; synthetic responder receive/reply/drop counters; restoration
  and verified namespace cleanup. DNS assertions verify that the live responder
  received 14 queries, deliberately ignored six and replied to the other eight.

A failed/interrupted rerun preserves its raw failure evidence and removes that
scenario's dashboard payload from the output directory. It cannot silently pair
an older successful dashboard with newer failed measurements.

Configured injection truth is kept separately from measured samples. The dashboard
source is `lab-drill`, with explicit synthetic-data limitations. These files
contain only synthetic lab targets. The incident duration is the span between
observed checks; it is not a claim of continuous monitoring between packets.

Open RoomFlow, set **Evidence source** to **Isolated fault drill**, then select
the delay, loss or DNS scenario. The server reads the saved dashboard payloads
from `results/incident-drills/`. The offline bundle also offers the scenario
switch when those files were present when the bundle was built. Read the event's
observed layers, uncertainty and next checks alongside the raw evidence. The
labels `internet` and `service` refer to the synthetic endpoints in this lab,
not actual Internet/meeting availability.

## Automated verification

The homepage can now play the saved measurements one at a time. Each step uses
the canonical incident engine's prefix result; later events, peaks and recovery
are hidden until that sample is reached. Event details include per-layer
numerical evidence and a healthy gateway comparison. Rebuild these presentation
files without touching the original packet evidence or sending new packets:

```sh
python scripts/rebuild-drill-dashboards.py
node scripts/build-observation-demo.mjs
```

```sh
python3 -m unittest discover -s lab -p test_incident_drill.py -v
```

Those portable tests check DNS response validation, latency/failure accounting,
evidence audit rejection and compatibility with incident replay. They do not
claim to run Linux packet faults. The separate **Incident faults and recovery**
GitHub Actions workflow actually runs all three scenarios on Ubuntu, fails on
any observation/transition/cleanup mismatch, and uploads raw evidence even when a
run fails. A newly added workflow is not evidence that remote CI has already run.
