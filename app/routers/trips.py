"""Saved trips - each user can only see and change their own."""

import json

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import session
from app.deps import delay_model, timetable, user_db
from app.schemas import TripIn
from app.security import current_user_id
from app.services.delay_model import DelayModel
from app.services.planner import build_journey, journey_to_dict
from app.services.timetable import Timetable

router = APIRouter(prefix="/api/trips", tags=["trips"])
MAX_TRIPS_PER_USER = 100


def _row_to_trip(row) -> dict:
    d = dict(row)
    d["legs"] = json.loads(d.pop("legs_json"))
    d.pop("user_id", None)
    return d


@router.get("")
def list_trips(user_id: int = Depends(current_user_id), path=Depends(user_db)):
    with session(path) as conn:
        rows = conn.execute("SELECT * FROM trips WHERE user_id = ? ORDER BY travel_date, id",
                            (user_id,)).fetchall()
    return [_row_to_trip(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_trip(body: TripIn, user_id: int = Depends(current_user_id), path=Depends(user_db),
                tt: Timetable = Depends(timetable), model: DelayModel = Depends(delay_model)):
    spec = [(leg.train_number, leg.from_code, leg.to_code) for leg in body.legs]
    try:
        journey = build_journey(tt, model, spec, body.travel_date, body.travel_class)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    data = journey_to_dict(journey, tt)
    fare_total = data["fare"] * body.passengers
    with session(path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM trips WHERE user_id = ?", (user_id,)).fetchone()[0]
        if count >= MAX_TRIPS_PER_USER:
            raise HTTPException(409, f"Trip limit reached ({MAX_TRIPS_PER_USER})")
        cur = conn.execute(
            """INSERT INTO trips (user_id, from_code, to_code, travel_date, travel_class,
                                  passengers, legs_json, fare_total, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, spec[0][1], spec[-1][2], body.travel_date.isoformat(), body.travel_class,
             body.passengers, json.dumps(data["legs"]), fare_total, body.note),
        )
        row = conn.execute("SELECT * FROM trips WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_trip(row)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(trip_id: int, user_id: int = Depends(current_user_id), path=Depends(user_db)):
    with session(path) as conn:
        cur = conn.execute("DELETE FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id))
    if cur.rowcount == 0:   # same response whether it doesn't exist or belongs to someone else
        raise HTTPException(404, "Trip not found")
