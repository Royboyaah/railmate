"""
Build the RailMate SQLite database from the public DataMeet Indian Railways dataset.

Source  : https://github.com/datameet/railways  (licence: CC0 / public domain)
Snapshot: the dataset was compiled around 2016-2017, so timings are historical.

Cleaning steps (each one is counted in the data-quality report):
  1. Schedules include pass-through timing points (arrival == departure).
     Only real halts are kept: origin, terminus, or a stop with dwell time.
  2. The "day" field is unreliable/missing in ~13% of rows, so day offsets are
     re-derived from the clock wrapping past midnight.
  3. Small backward time steps (data glitches) are clamped, not read as +1 day.
  4. Per-stop distances are not provided. They are computed from station
     coordinates (haversine), scaled to the train's official distance, and
     interpolated by time where coordinates are missing or inconsistent.

Usage (from the project root):
  python -m scripts.build_dataset                 # download + build
  python -m scripts.build_dataset --source DIR    # use already-downloaded JSON files
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import logging
import math
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from app.config import BASE_DIR, get_settings
from app.db import TIMETABLE_SCHEMA, init_schema, session

log = logging.getLogger("railmate.build")

RAW_BASE = "https://raw.githubusercontent.com/datameet/railways/master/"
FILES = ("stations.json", "trains.json", "schedules.json")

TYPE_LABELS = {
    "Pass": "Passenger", "Exp": "Express", "SF": "Superfast", "Mail": "Mail",
    "Raj": "Rajdhani", "Shtb": "Shatabdi", "JShtb": "Jan Shatabdi", "Drnt": "Duronto",
    "GR": "Garib Rath", "SKr": "Sampark Kranti", "MEMU": "MEMU", "DEMU": "DEMU",
    "Hyd": "Suburban", "Del": "Suburban", "Klkt": "Suburban", "Toy": "Toy Train",
}
CLASS_FLAGS = (("first_ac", "1A"), ("second_ac", "2A"), ("third_ac", "3A"),
               ("sleeper", "SL"), ("chair_car", "CC"))
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
GLITCH_TOLERANCE_MIN = 180   # backward steps smaller than this are data errors, not midnight


# ----------------------------------------------------------------- helpers
def parse_clock(value) -> int | None:
    if value in (None, "None", ""):
        return None
    parts = str(value).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def assign_absolute_times(rows: list[dict], stats: dict) -> None:
    """Add arr_abs / dep_abs = minutes since 00:00 on the train's origin day."""
    prev_abs = None
    offset = 0
    for row in rows:
        for key_in, key_out in (("arrival", "arr_abs"), ("departure", "dep_abs")):
            clock = parse_clock(row.get(key_in))
            if clock is None:
                row[key_out] = None
                continue
            value = offset * 1440 + clock
            if prev_abs is not None and value < prev_abs:
                if prev_abs - value < GLITCH_TOLERANCE_MIN:
                    stats["time_glitches_clamped"] += 1
                    value = prev_abs
                else:
                    while value < prev_abs:
                        offset += 1
                        value += 1440
            row[key_out] = value
            prev_abs = value


def is_halt(row: dict, index: int, last: int) -> bool:
    if index in (0, last):
        return True
    a, d = row.get("arr_abs"), row.get("dep_abs")
    return a is not None and d is not None and d > a


def assign_distances(rows: list[dict], coords: dict, total_km: float, stats: dict) -> None:
    """Add 'km' (distance from origin) to every row."""
    times = [r["dep_abs"] if r["dep_abs"] is not None else r["arr_abs"] for r in rows]
    t0, t_end = times[0], times[-1]

    def by_time():
        span = max(t_end - t0, 1)
        for r, t in zip(rows, times, strict=False):
            r["km"] = round(total_km * (t - t0) / span, 1)

    known = [(i, coords.get(r["station_code"])) for i, r in enumerate(rows)]
    known = [(i, c) for i, c in known if c]
    if len(known) < 2:
        stats["distance_by_time"] += 1
        return by_time()

    cum = {known[0][0]: 0.0}
    run = 0.0
    for (_i0, c0), (i1, c1) in zip(known, known[1:], strict=False):
        run += haversine_km(c0[0], c0[1], c1[0], c1[1])
        cum[i1] = run
    if run <= 0:
        stats["distance_by_time"] += 1
        return by_time()

    factor = total_km / run
    if not 0.8 <= factor <= 2.5:          # coordinates inconsistent with official distance
        stats["distance_by_time"] += 1
        return by_time()

    idx = sorted(cum)
    for i, r in enumerate(rows):
        if i in cum:
            km = cum[i]
        elif i < idx[0]:
            km = 0.0
        elif i > idx[-1]:
            km = cum[idx[-1]]
        else:   # interpolate by time between neighbouring known points
            pos = bisect.bisect_left(idx, i)
            lo, hi = idx[pos - 1], idx[pos]
            span = max(times[hi] - times[lo], 1)
            km = cum[lo] + (cum[hi] - cum[lo]) * (times[i] - times[lo]) / span
        r["km"] = round(km * factor, 1)
    rows[-1]["km"] = round(total_km, 1)


def tidy_name(name: str) -> str:
    """Source names mix ALL CAPS and Title Case; normalise mostly-uppercase names."""
    name = " ".join((name or "").split())
    letters = [c for c in name if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.6:
        name = name.title()
    return name


def parse_days(text: str) -> int:
    text = text.strip()
    if text.lower() == "daily":
        return 127
    mask = 0
    for token in text.replace(",", " ").split():
        mask |= 1 << DAY_NAMES.index(token[:3].title())
    return mask


# ----------------------------------------------------------------- build
def download(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = dest / name
        if target.exists():
            log.info("Using cached %s", target)
            continue
        log.info("Downloading %s ...", name)
        urllib.request.urlretrieve(RAW_BASE + name, target)  # noqa: S310 (fixed https URL)


def build(source: Path, db_path: Path, running_days_csv: Path | None = None) -> dict:
    stations = json.loads((source / "stations.json").read_text(encoding="utf-8"))["features"]
    trains = json.loads((source / "trains.json").read_text(encoding="utf-8"))["features"]
    schedules = json.loads((source / "schedules.json").read_text(encoding="utf-8"))

    stats = {"schedule_rows": len(schedules), "time_glitches_clamped": 0,
             "distance_by_time": 0, "trains_skipped": 0, "halts": 0,
             "rows_without_time_dropped": 0}

    coords, station_rows = {}, {}
    for f in stations:
        p = f["properties"]
        geo = f.get("geometry")
        lat = lon = None
        if geo and geo.get("coordinates"):
            lon, lat = geo["coordinates"][:2]
            coords[p["code"]] = (lat, lon)
        station_rows[p["code"]] = (p["code"], (p.get("name") or p["code"]).title(),
                                   p.get("state"), p.get("zone"), lat, lon)

    by_train: dict[str, list[dict]] = {}
    for s in schedules:
        by_train.setdefault(s["train_number"], []).append(s)

    running_days = {}
    if running_days_csv and running_days_csv.exists():
        with running_days_csv.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                running_days[row["train_number"].strip()] = parse_days(row["days"])

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    init_schema(db_path, TIMETABLE_SCHEMA)

    halt_counter: dict[str, set] = {}
    with session(db_path) as conn:
        conn.executemany("INSERT INTO stations (code, name, state, zone, lat, lon) VALUES (?,?,?,?,?,?)",
                         station_rows.values())
        for f in trains:
            p = f["properties"]
            rows = sorted(by_train.get(p["number"], []), key=lambda r: r["id"])
            before = len(rows)
            rows = [r for r in rows if r["station_code"] in station_rows
                    and (parse_clock(r.get("arrival")) is not None
                         or parse_clock(r.get("departure")) is not None)]
            stats["rows_without_time_dropped"] += before - len(rows)
            if len(rows) < 2 or not p.get("distance"):
                stats["trains_skipped"] += 1
                continue
            assign_absolute_times(rows, stats)
            if rows[0]["dep_abs"] is None or rows[-1]["arr_abs"] is None:
                stats["trains_skipped"] += 1
                continue
            assign_distances(rows, coords, float(p["distance"]), stats)
            last = len(rows) - 1
            halts = [r for i, r in enumerate(rows) if is_halt(r, i, last)]
            duration = halts[-1]["arr_abs"] - halts[0]["dep_abs"]
            if len(halts) < 2 or duration <= 0:
                stats["trains_skipped"] += 1
                continue

            classes = [code for flag, code in CLASS_FLAGS if p.get(flag)] or ["GN"]
            mask = running_days.get(p["number"])
            conn.execute(
                "INSERT INTO trains VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (p["number"], tidy_name(p["name"]), TYPE_LABELS.get(p.get("type"), "Other"), p.get("zone"),
                 halts[0]["station_code"], halts[-1]["station_code"], float(p["distance"]),
                 duration, ",".join(classes), mask if mask is not None else 127, int(mask is not None)),
            )
            conn.executemany(
                "INSERT INTO stops VALUES (?,?,?,?,?,?)",
                [(p["number"], seq, h["station_code"],
                  None if seq == 0 else h["arr_abs"],
                  None if seq == len(halts) - 1 else h["dep_abs"], h["km"])
                 for seq, h in enumerate(halts)],
            )
            stats["halts"] += len(halts)
            for h in halts:
                halt_counter.setdefault(h["station_code"], set()).add(p["number"])

        conn.executemany("UPDATE stations SET train_count = ? WHERE code = ?",
                         [(len(v), k) for k, v in halt_counter.items()])
        stats["trains_loaded"] = conn.execute("SELECT COUNT(*) FROM trains").fetchone()[0]
        stats["stations_served"] = len(halt_counter)
        stats["trains_with_running_days"] = len(running_days)
        meta = {
            "source": "DataMeet Indian Railways dataset (github.com/datameet/railways)",
            "license": "CC0 1.0 (public domain)",
            "snapshot_note": "Historical snapshot (circa 2016-17). Not live or current timings.",
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "quality": json.dumps(stats),
        }
        conn.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
    return stats


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=BASE_DIR / "data" / "raw",
                    help="folder holding stations.json, trains.json, schedules.json")
    ap.add_argument("--db", type=Path, default=get_settings().db_path)
    ap.add_argument("--running-days", type=Path, default=BASE_DIR / "data" / "running_days.csv")
    ap.add_argument("--no-download", action="store_true")
    args = ap.parse_args(argv)

    if not args.no_download:
        download(args.source)
    stats = build(args.source, args.db, args.running_days)
    log.info("Database written to %s", args.db)
    for k, v in stats.items():
        log.info("  %-28s %s", k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
