"""Journey search and train details."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import delay_model, timetable
from app.services.delay_model import DelayModel
from app.services.fares import CLASS_LABELS
from app.services.planner import DELAY_THRESHOLD_LABEL, PRIORITY_WEIGHTS, journey_to_dict, plan
from app.services.timetable import Timetable

router = APIRouter(prefix="/api", tags=["journeys"])

MAX_DAYS_AHEAD = 120


@router.get("/classes")
def classes():
    return CLASS_LABELS


@router.get("/journeys")
def search_journeys(
    from_code: str = Query(..., alias="from", min_length=1, max_length=6),
    to_code: str = Query(..., alias="to", min_length=1, max_length=6),
    travel_date: date | None = Query(None, alias="date"),
    travel_class: str = Query("3A", alias="class"),
    priority: str = "balanced",
    transfers: bool = True,
    tt: Timetable = Depends(timetable),
    model: DelayModel = Depends(delay_model),
):
    a, b = from_code.upper(), to_code.upper()
    travel_date = travel_date or date.today()
    if a not in tt.stations or b not in tt.stations:
        raise HTTPException(404, "Unknown station code")
    if a == b:
        raise HTTPException(422, "Origin and destination must be different")
    if travel_class not in CLASS_LABELS:
        raise HTTPException(422, f"class must be one of {list(CLASS_LABELS)}")
    if priority not in PRIORITY_WEIGHTS:
        raise HTTPException(422, f"priority must be one of {list(PRIORITY_WEIGHTS)}")
    if travel_date < date.today():
        raise HTTPException(422, "Travel date cannot be in the past")
    if travel_date > date.today() + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(422, f"Travel date must be within {MAX_DAYS_AHEAD} days")

    journeys = plan(tt, model, a, b, travel_date, travel_class, priority, transfers)
    return {
        "query": {"from": a, "to": b, "date": travel_date.isoformat(), "class": travel_class,
                  "priority": priority, "transfers": transfers},
        "count": len(journeys),
        "delay_definition": DELAY_THRESHOLD_LABEL,
        "model_status": model.status,
        "results": [journey_to_dict(j, tt) for j in journeys],
    }


@router.get("/trains/{number}")
def train_details(number: str, tt: Timetable = Depends(timetable)):
    t = tt.trains.get(number.upper())
    if t is None:
        raise HTTPException(404, "Train not found")

    def clock(m):
        return None if m is None else f"{(m % 1440) // 60:02d}:{m % 60:02d}"

    return {
        "number": t.number, "name": t.name, "type": t.type, "zone": t.zone,
        "classes": [{"code": c, "label": CLASS_LABELS.get(c, c)} for c in t.classes],
        "running_days": t.running_days_label,
        "distance_km": t.distance_km, "duration_min": t.duration_min,
        "halts": [{
            "seq": h.seq, "code": h.station,
            "name": tt.stations[h.station].name if h.station in tt.stations else h.station,
            "arrival": clock(h.arr), "departure": clock(h.dep),
            "day": ((h.dep if h.dep is not None else h.arr) // 1440) + 1,
            "km": h.km,
        } for h in t.halts],
    }
