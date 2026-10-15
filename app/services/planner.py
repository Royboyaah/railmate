"""
Journey planner: direct and one-transfer journeys, scoring and risk.

Time convention: every journey is expressed in minutes from 00:00 on the
travel date (the date the passenger boards at the origin station).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.services.delay_model import DelayModel, leg_features, missed_connection_risk
from app.services.fares import estimate_fare
from app.services.geo import haversine_km
from app.services.timetable import Halt, Timetable, Train

MIN_LAYOVER = 45      # minutes
MAX_LAYOVER = 360     # minutes
MAX_TRANSFER_RESULTS = 8
DELAY_THRESHOLD_LABEL = "more than 30 min late"

PRIORITY_WEIGHTS = {
    #            speed, cost, reliability, convenience
    "balanced": (0.30, 0.30, 0.25, 0.15),
    "fastest":  (0.55, 0.15, 0.15, 0.15),
    "cheapest": (0.15, 0.55, 0.15, 0.15),
    "reliable": (0.15, 0.15, 0.55, 0.15),
}


@dataclass
class Leg:
    train: Train
    board: Halt
    alight: Halt
    start: int          # minutes from 00:00 on travel date, departure from board
    fare: int = 0
    p_delay: float = 0.0

    @property
    def duration(self) -> int:
        return self.alight.arr - self.board.dep

    @property
    def end(self) -> int:
        return self.start + self.duration

    @property
    def km(self) -> float:
        return round(self.alight.km - self.board.km, 1)


@dataclass
class Journey:
    legs: list[Leg]
    travel_date: date
    layover: int = 0
    connection_risk: float = 0.0
    scores: dict = field(default_factory=dict)

    @property
    def total_minutes(self) -> int:
        return self.legs[-1].end - self.legs[0].start

    @property
    def km(self) -> float:
        return round(sum(leg.km for leg in self.legs), 1)

    @property
    def fare(self) -> int:
        return sum(leg.fare for leg in self.legs)


# ------------------------------------------------------------------ helpers
def _origin_date(travel_date: date, day_offset_from_origin: int) -> date:
    return travel_date - timedelta(days=day_offset_from_origin)


def _runs(train: Train, board: Halt, boarding_date: date) -> bool:
    """Check the train's ORIGIN date (not the boarding date) against its running days."""
    return train.runs_on_weekday(_origin_date(boarding_date, board.dep // 1440).weekday())


def _clock(minutes: int) -> str:
    return f"{(minutes % 1440) // 60:02d}:{minutes % 60:02d}"


def _best_pair(train: Train, a: str, b: str) -> tuple[Halt, Halt] | None:
    """Shortest board/alight pair (handles trains that visit a station twice)."""
    best = None
    for i, h in enumerate(train.halts):
        if h.station != a or h.dep is None:
            continue
        for h2 in train.halts[i + 1:]:
            if h2.station == b and h2.arr is not None:
                if best is None or (h2.arr - h.dep) < (best[1].arr - best[0].dep):
                    best = (h, h2)
                break
    return best


def _class_ok(train: Train, travel_class: str) -> bool:
    return travel_class in train.classes


# ------------------------------------------------------------------ search
def find_direct(tt: Timetable, a: str, b: str, travel_date: date, travel_class: str) -> list[Journey]:
    journeys = []
    seen = set()
    for number, _seq in tt.by_station.get(a, []):
        if number in seen:
            continue
        seen.add(number)
        train = tt.trains[number]
        if not _class_ok(train, travel_class):
            continue
        pair = _best_pair(train, a, b)
        if not pair or not _runs(train, pair[0], travel_date):
            continue
        board, alight = pair
        journeys.append(Journey([Leg(train, board, alight, start=board.dep % 1440)], travel_date))
    return journeys


def find_one_transfer(tt: Timetable, a: str, b: str, travel_date: date, travel_class: str,
                      exclude_direct_trains: set[str]) -> list[Journey]:
    # Transfer stations must make geographic progress towards B (no backtracking).
    def dist_to_b(code: str) -> float | None:
        s1, s2 = tt.stations.get(code), tt.stations.get(b)
        if not s1 or not s2 or s1.lat is None or s2.lat is None:
            return None
        return haversine_km(s1.lat, s1.lon, s2.lat, s2.lon)

    a_to_b = dist_to_b(a)
    progress_cache: dict[str, bool] = {}

    def makes_progress(code: str) -> bool:
        if code not in progress_cache:
            d = dist_to_b(code)
            progress_cache[code] = a_to_b is None or d is None or d < a_to_b * 0.9
        return progress_cache[code]

    # arrivals[S] = legs from A that reach S ; departures[S] = legs from S that reach B
    arrivals: dict[str, list[tuple[Train, Halt, Halt]]] = {}
    for number, seq in tt.by_station.get(a, []):
        train = tt.trains[number]
        if number in exclude_direct_trains or not _class_ok(train, travel_class):
            continue
        board = train.halts[seq]
        if board.dep is None or not _runs(train, board, travel_date):
            continue
        for h in train.halts[seq + 1:]:
            if h.station not in (a, b) and h.arr is not None and makes_progress(h.station):
                arrivals.setdefault(h.station, []).append((train, board, h))

    departures: dict[str, list[tuple[Train, Halt, Halt]]] = {}
    for number, seq in tt.by_station.get(b, []):
        train = tt.trains[number]
        if number in exclude_direct_trains or not _class_ok(train, travel_class):
            continue
        alight = train.halts[seq]
        if alight.arr is None:
            continue
        for h in train.halts[:seq]:
            if h.station in arrivals and h.dep is not None:
                departures.setdefault(h.station, []).append((train, h, alight))

    best_per_pair: dict[tuple[str, str], Journey] = {}
    for station, outs in departures.items():
        for t1, board1, at_s in arrivals[station]:
            start1 = board1.dep % 1440
            arrive_s = start1 + (at_s.arr - board1.dep)
            for t2, board2, alight2 in outs:
                if t1.number == t2.number:
                    continue
                layover = (board2.dep % 1440 - arrive_s) % 1440
                if layover < MIN_LAYOVER or layover > MAX_LAYOVER:
                    continue
                start2 = arrive_s + layover
                leg2_date = travel_date + timedelta(days=start2 // 1440)
                if not _runs(t2, board2, leg2_date):
                    continue
                j = Journey([Leg(t1, board1, at_s, start1), Leg(t2, board2, alight2, start2)],
                            travel_date, layover=layover)
                key = (t1.number, t2.number)
                if key not in best_per_pair or j.total_minutes < best_per_pair[key].total_minutes:
                    best_per_pair[key] = j

    ranked = sorted(best_per_pair.values(), key=lambda j: j.total_minutes)
    # keep variety: at most two options per first train
    result, per_first = [], {}
    for j in ranked:
        n = j.legs[0].train.number
        if per_first.get(n, 0) >= 2:
            continue
        per_first[n] = per_first.get(n, 0) + 1
        result.append(j)
        if len(result) >= MAX_TRANSFER_RESULTS:
            break
    return result


# ------------------------------------------------------------------ enrichment
def enrich(journeys: list[Journey], travel_class: str, model: DelayModel) -> None:
    """Add fares, delay probabilities and connection risk."""
    rows, legs = [], []
    for j in journeys:
        for leg in j.legs:
            leg.fare = estimate_fare(leg.km, travel_class, leg.train.type)
            leg_date = j.travel_date + timedelta(days=leg.start // 1440)
            rows.append(leg_features(leg.train, leg.board, leg.alight, leg_date))
            legs.append(leg)
    for leg, p in zip(legs, model.predict(rows), strict=False):
        leg.p_delay = p
    for j in journeys:
        if len(j.legs) == 2:
            j.connection_risk = missed_connection_risk(j.legs[0].p_delay, j.layover)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def score(j: Journey, travel_class: str, priority: str) -> None:
    """Absolute 0-100 sub-scores, so scores are comparable across different searches."""
    hours = max(j.total_minutes / 60, 0.1)
    speed = _clamp((j.km / hours - 20) / 65)                       # 20 km/h -> 0, 85 km/h -> 1
    reference = estimate_fare(j.km, travel_class, "Express")       # plain express fare
    cost = _clamp((1.5 - j.fare / reference) / 0.8)
    p_late = 1 - (1 - j.legs[-1].p_delay) * (1 - j.connection_risk)
    reliability = 1 - p_late
    convenience = 1.0 - 0.3 * (len(j.legs) - 1)
    dep_hour = (j.legs[0].start % 1440) // 60
    arr_hour = (j.legs[-1].end % 1440) // 60
    if dep_hour < 5:
        convenience -= 0.15
    if arr_hour < 5:
        convenience -= 0.10
    if j.layover > 180:
        convenience -= 0.10
    convenience = _clamp(convenience)

    w = PRIORITY_WEIGHTS[priority]
    parts = {"speed": speed, "cost": cost, "reliability": reliability, "convenience": convenience}
    j.scores = {
        "total": round(100 * sum(wi * v for wi, v in zip(w, parts.values(), strict=False)), 1),
        **{k: round(100 * v) for k, v in parts.items()},
        "p_late": round(p_late, 3),
    }


def _dedupe(journeys: list[Journey]) -> list[Journey]:
    """Different weekly trains often share one timetable slot; show each slot once."""
    seen, out = set(), []
    for j in journeys:
        sig = tuple((leg.board.station, leg.start % 1440, leg.alight.station, leg.duration) for leg in j.legs)
        if sig not in seen:
            seen.add(sig)
            out.append(j)
    return out


def risk_level(p: float) -> str:
    return "Low" if p < 0.25 else "Medium" if p < 0.45 else "High"


def plan(tt: Timetable, model: DelayModel, a: str, b: str, travel_date: date,
         travel_class: str, priority: str, include_transfers: bool = True) -> list[Journey]:
    direct = find_direct(tt, a, b, travel_date, travel_class)
    transfers = []
    if include_transfers:
        transfers = find_one_transfer(tt, a, b, travel_date, travel_class,
                                      {j.legs[0].train.number for j in direct})
        if direct:   # only show transfers that are clearly competitive
            fastest = min(j.total_minutes for j in direct)
            transfers = [t for t in transfers if t.total_minutes < fastest * 1.25]
    journeys = _dedupe(direct + transfers)
    enrich(journeys, travel_class, model)
    for j in journeys:
        score(j, travel_class, priority)
    journeys.sort(key=lambda j: j.scores["total"], reverse=True)
    return journeys


# ------------------------------------------------------------------ serialisation
def leg_to_dict(leg: Leg, tt: Timetable) -> dict:
    st = tt.stations
    return {
        "train_number": leg.train.number,
        "train_name": leg.train.name,
        "train_type": leg.train.type,
        "running_days": leg.train.running_days_label,
        # Indian Railways numbers seasonal/special trains starting with 0
        "special": leg.train.number.startswith("0"),
        "from_code": leg.board.station,
        "from_name": st[leg.board.station].name if leg.board.station in st else leg.board.station,
        "to_code": leg.alight.station,
        "to_name": st[leg.alight.station].name if leg.alight.station in st else leg.alight.station,
        "departure": _clock(leg.start),
        "departure_day": leg.start // 1440,
        "arrival": _clock(leg.end),
        "arrival_day": leg.end // 1440,
        "duration_min": leg.duration,
        "distance_km": leg.km,
        "fare": leg.fare,
        "p_delay": leg.p_delay,
    }


def journey_to_dict(j: Journey, tt: Timetable) -> dict:
    return {
        "id": "-".join(f"{leg.train.number}@{leg.board.station}" for leg in j.legs),
        "transfers": len(j.legs) - 1,
        "legs": [leg_to_dict(leg, tt) for leg in j.legs],
        "layover_min": j.layover or None,
        "connection_risk": j.connection_risk if len(j.legs) > 1 else None,
        "total_minutes": j.total_minutes,
        "distance_km": j.km,
        "fare": j.fare,
        "scores": j.scores,
        "delay_risk": risk_level(j.scores.get("p_late", 0)),
    }


def build_journey(tt: Timetable, model: DelayModel, legs_spec: list[tuple[str, str, str]],
                  travel_date: date, travel_class: str) -> Journey:
    """
    Rebuild and validate a journey from (train_number, from_code, to_code) legs.
    Used when saving trips so the server never trusts client-supplied times or fares.
    Raises ValueError with a user-facing message.
    """
    if not 1 <= len(legs_spec) <= 2:
        raise ValueError("A trip must have one or two legs")
    legs: list[Leg] = []
    layover = 0
    for i, (number, frm, to) in enumerate(legs_spec):
        train = tt.trains.get(number)
        if train is None:
            raise ValueError(f"Unknown train {number}")
        if not _class_ok(train, travel_class):
            raise ValueError(f"Train {number} has no {travel_class} class")
        pair = _best_pair(train, frm, to)
        if pair is None:
            raise ValueError(f"Train {number} does not run from {frm} to {to}")
        board, alight = pair
        if i == 0:
            start = board.dep % 1440
            leg_date = travel_date
        else:
            prev = legs[-1]
            if prev.alight.station != frm:
                raise ValueError("The second leg must start where the first leg ends")
            layover = (board.dep % 1440 - prev.end) % 1440
            if not MIN_LAYOVER <= layover <= MAX_LAYOVER:
                raise ValueError("Connection layover must be between 45 minutes and 6 hours")
            start = prev.end + layover
            leg_date = travel_date + timedelta(days=start // 1440)
        if not _runs(train, board, leg_date):
            raise ValueError(f"Train {number} does not run on the selected date")
        legs.append(Leg(train, board, alight, start))
    journey = Journey(legs, travel_date, layover=layover)
    enrich([journey], travel_class, model)
    return journey
