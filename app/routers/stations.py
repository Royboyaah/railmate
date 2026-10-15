"""Station search (autocomplete) and details."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import timetable
from app.services.timetable import Timetable

router = APIRouter(prefix="/api/stations", tags=["stations"])


def _station(s) -> dict:
    return {"code": s.code, "name": s.name, "state": s.state, "zone": s.zone,
            "train_count": s.train_count}


@router.get("")
def search_stations(q: str = Query("", max_length=60), limit: int = Query(10, ge=1, le=25),
                    tt: Timetable = Depends(timetable)):
    """Autocomplete by station name or code, most-served stations first."""
    return [_station(s) for s in tt.search_stations(q, limit)]


@router.get("/{code}")
def get_station(code: str, tt: Timetable = Depends(timetable)):
    s = tt.stations.get(code.upper())
    if s is None:
        raise HTTPException(404, "Station not found")
    return _station(s)
