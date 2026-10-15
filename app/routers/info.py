"""Health, help desk and insights."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db import get_meta, session
from app.deps import delay_model, helpdesk, user_db
from app.services.delay_model import DelayModel
from app.services.helpdesk import HelpDesk

router = APIRouter(prefix="/api", tags=["info"])


@router.get("/health")
def health(request: Request):
    tt = request.app.state.timetable
    return {
        "status": "ok" if tt.loaded else "degraded",
        "timetable_loaded": tt.loaded,
        "trains": len(tt.trains),
        "delay_model": request.app.state.delay_model.status,
        "version": request.app.version,
    }


@router.get("/helpdesk")
def ask(q: str = Query("", max_length=300), desk: HelpDesk = Depends(helpdesk)):
    return desk.answer(q)


@router.get("/helpdesk/topics")
def topics(desk: HelpDesk = Depends(helpdesk)):
    return desk.topics()


@router.get("/insights")
def insights(request: Request, users_path=Depends(user_db), model: DelayModel = Depends(delay_model)):
    tt = request.app.state.timetable
    if not tt.loaded:
        raise HTTPException(503, "Timetable not loaded. Run: python -m scripts.build_dataset")
    with session(request.app.state.settings.db_path) as conn:
        meta = get_meta(conn)
        types = conn.execute("SELECT type, COUNT(*) AS n FROM trains GROUP BY type ORDER BY n DESC").fetchall()
        busiest = conn.execute(
            "SELECT code, name, train_count FROM stations ORDER BY train_count DESC LIMIT 10").fetchall()
    with session(users_path) as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        trips = conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    return {
        "dataset": {
            "source": meta.get("source"), "license": meta.get("license"),
            "note": meta.get("snapshot_note"), "built_at": meta.get("built_at"),
            "quality": json.loads(meta["quality"]) if "quality" in meta else {},
            "trains": len(tt.trains), "stations": len(tt.stations),
        },
        "train_types": [dict(r) for r in types],
        "busiest_stations": [dict(r) for r in busiest],
        "usage": {"users": users, "saved_trips": trips},
        "model": {"status": model.status, **model.card},
    }
