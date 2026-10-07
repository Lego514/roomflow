"""Wi-Fi channel analysis: how crowded is my channel, and is there a quieter one?

In a dense apartment building dozens of access points share a few channels.
Wi-Fi is half-duplex and polite: before sending, a radio listens, and if any
other network on an overlapping channel is talking, it waits. So neighbors on
your channel don't just add noise, they take airtime. This module counts them
per channel, groups 5 GHz channels into the 80 MHz blocks modern routers use,
and suggests the least crowded block.

Only radio facts are used (band, channel, signal, utilization). Neighbors'
network names and MAC addresses are never read into memory.
"""

from __future__ import annotations

from dataclasses import dataclass

from .measure import Bss


@dataclass(frozen=True)
class ChannelStat:
    count: int  # access points (BSSIDs) heard on this channel
    strongest: int  # strongest signal among them, in Windows' 0-100 %


def count_by_channel(bss: list[Bss]) -> dict[tuple[str, int], ChannelStat]:
    """Group access points by (band, channel): how many, and the strongest signal.

    The key includes the band because channel numbers repeat across bands:
    2.4 GHz channel 1 and 6 GHz channel 1 are different frequencies. Access
    points with an unknown band or channel are skipped. One with an unknown
    signal still counts, but can't change the strongest value.
    """
    totals: dict[tuple[str, int], list[int]] = {}  # key -> [count, strongest]
    for b in bss:
        if b.band is None or b.channel is None:
            continue
        entry = totals.setdefault((b.band, b.channel), [0, 0])
        entry[0] += 1
        if b.signal_pct is not None and b.signal_pct > entry[1]:
            entry[1] = b.signal_pct
    return {key: ChannelStat(count, strongest) for key, (count, strongest) in totals.items()}


# 5 GHz channels grouped into 80 MHz blocks. A router on channel 44 with an
# 80 MHz width also uses 36, 40 and 48, so a neighbor on 40 competes with it.
BLOCKS_5GHZ: list[tuple[int, ...]] = [
    (36, 40, 44, 48),
    (52, 56, 60, 64),
    (100, 104, 108, 112),
    (116, 120, 124, 128),
    (132, 136, 140, 144),
    (149, 153, 157, 161),
]
# 52-144 are DFS channels: the router must leave them if it detects radar, which
# causes a short outage. Worth knowing before recommending one for a call.
DFS = set(range(52, 145))


def block_of(channel: int) -> tuple[int, ...] | None:
    for block in BLOCKS_5GHZ:
        if channel in block:
            return block
    return None


@dataclass(frozen=True)
class BlockLoad:
    block: tuple[int, ...]
    count: int  # access points anywhere in the block
    strongest: int  # strongest neighbor signal in the block, 0 if none
    dfs: bool


def block_loads(stats: dict[tuple[str, int], ChannelStat]) -> list[BlockLoad]:
    """Neighbors per 5 GHz block, quietest first (weakest strongest neighbor, then fewest)."""
    loads = []
    for block in BLOCKS_5GHZ:
        in_block = [stats[("5 GHz", ch)] for ch in block if ("5 GHz", ch) in stats]
        loads.append(
            BlockLoad(
                block=block,
                count=sum(s.count for s in in_block),
                strongest=max((s.strongest for s in in_block), default=0),
                dfs=block[0] in DFS,
            )
        )
    # A strong neighbor hurts far more than several faint ones, so rank by the
    # strongest signal first. DFS blocks lose ties: radar can force a move.
    return sorted(loads, key=lambda b: (b.strongest, b.count, b.dfs))


def utilization_on(bss: list[Bss], band: str, channel: int) -> int | None:
    """Highest channel utilization any access point on this channel reports (Bss Load), in %.

    Includes our own router on purpose: utilization measures how busy the channel
    is for everyone, whoever reports it.
    """
    values = [b.utilization_pct for b in bss if b.band == band and b.channel == channel and b.utilization_pct is not None]
    return max(values) if values else None


@dataclass(frozen=True)
class ChannelAdvice:
    my_block: BlockLoad | None
    best: BlockLoad
    my_utilization: int | None
    text: str


def neighbors(bss: list[Bss]) -> list[Bss]:
    """Access points that aren't our own router: the ones competing for airtime."""
    return [b for b in bss if not b.own]


def advise(bss: list[Bss], my_band: str | None, my_channel: int | None) -> ChannelAdvice:
    stats = count_by_channel(neighbors(bss))
    loads = block_loads(stats)
    best = loads[0]
    mine_block = block_of(my_channel) if my_band == "5 GHz" and my_channel else None
    mine = next((b for b in loads if b.block == mine_block), None)
    util = utilization_on(bss, my_band, my_channel) if my_band and my_channel else None

    if my_band != "5 GHz":
        text = "You're on 2.4 GHz or 6 GHz; the block advice below is for 5 GHz."
    elif mine is None:
        text = "Your channel isn't in a standard 5 GHz block."
    elif mine.block == best.block:
        text = f"Your block {_fmt(mine.block)} is already the quietest one heard."
    else:
        text = (f"Your block {_fmt(mine.block)} has {mine.count} neighbor access points (strongest {mine.strongest}%). "
                f"Block {_fmt(best.block)} has {best.count} (strongest {best.strongest}%)"
                + (", but it is DFS: the router must leave it if it detects radar" if best.dfs else "") + ".")
    if mine is not None and mine.strongest >= 80:
        text += (f"\nA neighbor at {mine.strongest}% is about as loud as your own router. It may be next door, "
                 "or part of your own Wi-Fi system (a mesh node) that this scan can't link to your router.")
    return ChannelAdvice(mine, best, util, text)


def _fmt(block: tuple[int, ...]) -> str:
    return f"{block[0]}-{block[-1]}"
