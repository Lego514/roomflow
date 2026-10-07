"""Bufferbloat test: latency at idle, then while the link is saturated each way.

This is the home version of the lab's experiment. The lab built a bottleneck and
a roommate; here the bottleneck is the real router and ISP link, and the
"roommate" is a set of parallel transfers to Cloudflare's speed-test endpoints.

Latency is sampled two ways at the same time:
  - TCP handshakes to 1.1.1.1:443, five a second (internet path)
  - ping to the default gateway, once a second (the local hop: Wi-Fi + router)
If latency to the internet rises under load but the gateway stays flat, the
queue is upstream (modem/ISP); if the gateway rises too, it is local.
"""

from __future__ import annotations

import http.client
import os
import ssl
import threading
import time
from dataclasses import dataclass, field

from . import measure
from .stats import Series, bloat_grade

INTERNET_TARGET = "1.1.1.1"
SPEED_HOST = "speed.cloudflare.com"
DOWN_PATH = "/__down?bytes=25000000"  # larger requests get 403
REQUEST_BYTES = 25_000_000
HEADERS = {"User-Agent": "roomflow-homenet/0.1"}
UP_PATH = "/__up"
STREAMS = 4
CHUNK = 64 * 1024


@dataclass
class Phase:
    name: str  # "idle", "download", "upload"
    internet: Series = field(default_factory=lambda: Series(INTERNET_TARGET))
    gateway: Series = field(default_factory=lambda: Series("gateway"))
    bytes_moved: int = 0
    seconds: float = 0.0

    @property
    def mbps(self) -> float:
        return self.bytes_moved * 8 / self.seconds / 1e6 if self.seconds else 0.0


def _sample(stop: threading.Event, phase: Phase, gateway: str | None) -> list[threading.Thread]:
    def internet() -> None:
        while not stop.is_set():
            t = time.monotonic()
            phase.internet.add(measure.tcp_rtt(INTERNET_TARGET, 443))
            time.sleep(max(0.0, 0.2 - (time.monotonic() - t)))

    def local() -> None:
        while gateway and not stop.is_set():
            t = time.monotonic()
            phase.gateway.add(measure.ping_once(gateway))
            time.sleep(max(0.0, 1.0 - (time.monotonic() - t)))

    threads = [threading.Thread(target=internet, daemon=True), threading.Thread(target=local, daemon=True)]
    for th in threads:
        th.start()
    return threads


def _downloader(stop: threading.Event, counter: list[int], lock: threading.Lock) -> None:
    ctx = ssl.create_default_context()
    while not stop.is_set():
        conn = http.client.HTTPSConnection(SPEED_HOST, timeout=10, context=ctx)
        try:
            conn.request("GET", DOWN_PATH, headers=HEADERS)
            resp = conn.getresponse()
            while not stop.is_set():
                data = resp.read(CHUNK)
                if not data:
                    break
                with lock:
                    counter[0] += len(data)
        except OSError:
            time.sleep(0.5)
        finally:
            conn.close()


def _uploader(stop: threading.Event, counter: list[int], lock: threading.Lock) -> None:
    ctx = ssl.create_default_context()
    block = os.urandom(CHUNK)  # incompressible

    def body():
        sent = 0
        while not stop.is_set() and sent < REQUEST_BYTES:
            yield block
            sent += len(block)
            with lock:
                counter[0] += len(block)

    while not stop.is_set():
        conn = http.client.HTTPSConnection(SPEED_HOST, timeout=10, context=ctx)
        try:
            conn.request("POST", UP_PATH, body=body(), headers={**HEADERS, "Content-Type": "application/octet-stream"},
                         encode_chunked=True)
            conn.getresponse().read()
        except OSError:
            time.sleep(0.5)
        finally:
            conn.close()


def run_phase(name: str, seconds: float, gateway: str | None) -> Phase:
    phase = Phase(name)
    stop = threading.Event()
    counter, lock = [0], threading.Lock()
    workers: list[threading.Thread] = []
    if name in ("download", "upload"):
        target = _downloader if name == "download" else _uploader
        workers = [threading.Thread(target=target, args=(stop, counter, lock), daemon=True) for _ in range(STREAMS)]
        for w in workers:
            w.start()
        time.sleep(2)  # let TCP ramp up and fill the queue before measuring
        with lock:
            counter[0] = 0
    samplers = _sample(stop, phase, gateway)
    start = time.monotonic()
    time.sleep(seconds)
    phase.seconds = time.monotonic() - start
    with lock:
        phase.bytes_moved = counter[0]
    stop.set()
    for th in samplers + workers:
        th.join(timeout=12)
    return phase


@dataclass
class BloatResult:
    idle: Phase
    download: Phase
    upload: Phase

    def grade(self, phase: Phase) -> tuple[str, float | None, str]:
        return bloat_grade(self.idle.internet.p50, phase.internet.p95)


def bufferbloat(seconds: float = 10, gateway: str | None = None) -> BloatResult:
    gateway = gateway or measure.default_gateway()
    idle = run_phase("idle", seconds, gateway)
    down = run_phase("download", seconds, gateway)
    time.sleep(2)  # let the download queue drain
    up = run_phase("upload", seconds, gateway)
    return BloatResult(idle, down, up)
