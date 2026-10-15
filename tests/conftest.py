"""Shared fixtures: build a tiny dataset with the REAL importer, train a tiny model, start the app."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect
from app.main import create_app
from app.services.delay_model import DelayModel
from app.services.timetable import Timetable
from ml.train_delay_model import train
from scripts.build_dataset import build

FIXTURES = Path(__file__).parent / "fixtures"


def next_weekday(weekday: int) -> date:
    """Next date (at least 1 day ahead) falling on `weekday` (Mon=0)."""
    d = date.today() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("railmate")
    db = tmp / "timetable.db"
    stats = build(FIXTURES, db, FIXTURES / "running_days.csv")
    conn = connect(db)
    tt = Timetable.from_db(conn)
    conn.close()
    model_path = tmp / "model.joblib"
    train(tt, model_path, n=800, seed=1)
    return {"db": db, "stats": stats, "tt": tt, "model_path": model_path, "tmp": tmp}


@pytest.fixture(scope="session")
def tt(built) -> Timetable:
    return built["tt"]


@pytest.fixture(scope="session")
def model(built) -> DelayModel:
    return DelayModel(built["model_path"])


def make_settings(built, tmp_path: Path, rate_limit: int = 0) -> Settings:
    return Settings(env="test", db_path=built["db"], user_db_path=tmp_path / "users.db",
                    model_path=built["model_path"], secret_key="test-secret-key-for-tests-only-0123456789",
                    rate_limit_per_minute=rate_limit, log_level="WARNING")


@pytest.fixture
def client(built, tmp_path):
    with TestClient(create_app(make_settings(built, tmp_path))) as c:
        yield c


def register(client, email="user@example.com", password="secret123", name="Test User"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": name})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
