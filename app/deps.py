"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.services.delay_model import DelayModel
from app.services.helpdesk import HelpDesk
from app.services.timetable import Timetable


def timetable(request: Request) -> Timetable:
    tt: Timetable = request.app.state.timetable
    if not tt.loaded:
        raise HTTPException(503, "Timetable not loaded. Run: python -m scripts.build_dataset")
    return tt


def delay_model(request: Request) -> DelayModel:
    return request.app.state.delay_model


def helpdesk(request: Request) -> HelpDesk:
    return request.app.state.helpdesk


def user_db(request: Request):
    """Path of the user database (accounts and saved trips)."""
    return request.app.state.settings.user_db_path
