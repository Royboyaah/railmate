"""In-memory timetable index, loaded once from SQLite at startup for fast searching."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True, slots=True)
class Halt:
    seq: int
    station: str
    arr: int | None   # minutes since 00:00 on the origin day (None at origin)
    dep: int | None   # None at terminus
    km: float


@dataclass(slots=True)
class Train:
    number: str
    name: str
    type: str
    zone: str | None
    origin: str
    destination: str
    distance_km: float
    duration_min: int
    classes: tuple[str, ...]
    runs_on: int
    runs_on_known: bool
    halts: list[Halt] = field(default_factory=list)

    def runs_on_weekday(self, weekday: int) -> bool:
        """weekday: Monday=0 ... Sunday=6. Unknown schedules are assumed to run."""
        return (not self.runs_on_known) or bool(self.runs_on & (1 << weekday))

    @property
    def running_days_label(self) -> str:
        if not self.runs_on_known:
            return "Not in source data"
        if self.runs_on == 127:
            return "Daily"
        return ", ".join(d for i, d in enumerate(DAY_NAMES) if self.runs_on & (1 << i))


@dataclass(slots=True)
class Station:
    code: str
    name: str
    state: str | None
    zone: str | None
    lat: float | None
    lon: float | None
    train_count: int


class Timetable:
    def __init__(self) -> None:
        self.trains: dict[str, Train] = {}
        self.stations: dict[str, Station] = {}
        # station -> list of (train_number, seq)
        self.by_station: dict[str, list[tuple[str, int]]] = defaultdict(list)

    @property
    def loaded(self) -> bool:
        return bool(self.trains)

    @classmethod
    def from_db(cls, conn: sqlite3.Connection) -> Timetable:
        tt = cls()
        for r in conn.execute("SELECT * FROM stations WHERE train_count > 0"):
            tt.stations[r["code"]] = Station(r["code"], r["name"], r["state"], r["zone"],
                                             r["lat"], r["lon"], r["train_count"])
        for r in conn.execute("SELECT * FROM trains"):
            tt.trains[r["number"]] = Train(
                r["number"], r["name"], r["type"], r["zone"], r["origin"], r["destination"],
                r["distance_km"], r["duration_min"], tuple(r["classes"].split(",")),
                r["runs_on"], bool(r["runs_on_known"]),
            )
        for r in conn.execute("SELECT * FROM stops ORDER BY train_number, seq"):
            train = tt.trains.get(r["train_number"])
            if train is None:
                continue
            train.halts.append(Halt(r["seq"], r["station_code"], r["arr_min"], r["dep_min"], r["km"]))
            tt.by_station[r["station_code"]].append((train.number, r["seq"]))
        return tt

    def search_stations(self, query: str, limit: int = 10) -> list[Station]:
        q = query.strip().lower()
        if not q:
            return sorted(self.stations.values(), key=lambda s: -s.train_count)[:limit]
        scored = []
        for s in self.stations.values():
            code, name = s.code.lower(), s.name.lower()
            if code == q:
                rank = 0
            elif name.startswith(q):
                rank = 1
            elif code.startswith(q):
                rank = 2
            elif q in name:
                rank = 3
            else:
                continue
            scored.append((rank, -s.train_count, s.name, s))
        scored.sort(key=lambda x: x[:3])
        return [x[3] for x in scored[:limit]]
