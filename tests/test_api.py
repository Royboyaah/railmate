"""HTTP API: validation, auth, ownership, security headers, rate limiting."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings, next_weekday, register

TUE = next_weekday(1).isoformat()


def test_health_and_headers(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["delay_model"] == "model"
    for h in ("X-Request-ID", "Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options"):
        assert h in r.headers


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "RailMate" in r.text
    assert client.get("/static/js/app.js").status_code == 200


def test_station_autocomplete(client):
    r = client.get("/api/stations", params={"q": "alp"}).json()
    assert r[0]["code"] == "AAA"
    assert client.get("/api/stations/ZZZ").status_code == 404


def test_journey_search(client):
    r = client.get("/api/journeys", params={"from": "AAA", "to": "FFF", "date": TUE, "class": "SL"})
    body = r.json()
    assert r.status_code == 200 and body["count"] >= 1
    first = body["results"][0]
    assert {"legs", "scores", "fare", "delay_risk", "total_minutes"} <= first.keys()


def test_journey_validation(client):
    past = (date.today() - timedelta(days=1)).isoformat()
    far = (date.today() + timedelta(days=400)).isoformat()
    base = {"from": "AAA", "to": "DDD", "class": "SL"}
    assert client.get("/api/journeys", params={**base, "date": past}).status_code == 422
    assert client.get("/api/journeys", params={**base, "date": far}).status_code == 422
    assert client.get("/api/journeys", params={**base, "class": "XX"}).status_code == 422
    assert client.get("/api/journeys", params={**base, "to": "AAA"}).status_code == 422
    assert client.get("/api/journeys", params={**base, "to": "ZZZ"}).status_code == 404


def test_train_details(client):
    t = client.get("/api/trains/10001").json()
    assert [h["code"] for h in t["halts"]] == ["AAA", "CCC", "DDD"]
    assert client.get("/api/trains/99999").status_code == 404


def test_register_login_me(client):
    register(client, "a@example.com")
    r = client.post("/api/auth/login", json={"email": "A@Example.com", "password": "secret123"})
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["email"] == "a@example.com"


def test_auth_errors(client):
    register(client, "b@example.com")
    assert client.post("/api/auth/register", json={"email": "b@example.com", "password": "secret123",
                                                   "name": "X"}).status_code == 409
    assert client.post("/api/auth/register", json={"email": "c@example.com", "password": "password",
                                                   "name": "X"}).status_code == 422      # letters only
    assert client.post("/api/auth/register", json={"email": "not-an-email", "password": "secret123",
                                                   "name": "X"}).status_code == 422
    assert client.post("/api/auth/login", json={"email": "b@example.com",
                                                "password": "wrong-pass1"}).status_code == 401
    assert client.get("/api/trips").status_code == 401
    assert client.get("/api/trips", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_trip_lifecycle_and_ownership(client):
    alice = register(client, "alice@example.com")
    bob = register(client, "bob@example.com")
    payload = {"legs": [{"train_number": "10001", "from_code": "AAA", "to_code": "DDD"},
                        {"train_number": "10003", "from_code": "DDD", "to_code": "FFF"}],
               "travel_date": TUE, "travel_class": "SL", "passengers": 2, "note": "  test   trip "}
    r = client.post("/api/trips", json=payload, headers=alice)
    assert r.status_code == 201, r.text
    trip = r.json()
    assert trip["note"] == "test trip" and len(trip["legs"]) == 2
    assert trip["fare_total"] == 2 * sum(leg["fare"] for leg in trip["legs"])    # computed server-side

    assert len(client.get("/api/trips", headers=alice).json()) == 1
    assert client.get("/api/trips", headers=bob).json() == []
    assert client.delete(f"/api/trips/{trip['id']}", headers=bob).status_code == 404   # not his
    assert client.delete(f"/api/trips/{trip['id']}", headers=alice).status_code == 204
    assert client.get("/api/trips", headers=alice).json() == []


def test_trip_validation(client):
    h = register(client, "carol@example.com")
    bad_route = {"legs": [{"train_number": "10001", "from_code": "DDD", "to_code": "AAA"}],
                 "travel_date": TUE, "travel_class": "SL"}
    assert client.post("/api/trips", json=bad_route, headers=h).status_code == 422
    too_many = {"legs": [{"train_number": "10001", "from_code": "AAA", "to_code": "DDD"}],
                "travel_date": TUE, "travel_class": "SL", "passengers": 9}
    assert client.post("/api/trips", json=too_many, headers=h).status_code == 422


def test_helpdesk(client):
    assert client.get("/api/helpdesk", params={"q": "what is rac"}).json()["matched"] is True
    assert client.get("/api/helpdesk", params={"q": "best pizza in town"}).json()["matched"] is False
    assert len(client.get("/api/helpdesk/topics").json()) >= 20


def test_insights(client):
    d = client.get("/api/insights").json()
    assert d["dataset"]["trains"] == 5
    assert d["model"]["synthetic"] is True
    assert "roc_auc" in d["model"]["metrics"]


def test_rate_limit(built, tmp_path):
    with TestClient(create_app(make_settings(built, tmp_path, rate_limit=3))) as c:
        codes = [c.get("/api/health").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_missing_timetable_degrades_gracefully(built, tmp_path):
    s = make_settings(built, tmp_path)
    object.__setattr__(s, "db_path", tmp_path / "missing.db")
    with TestClient(create_app(s)) as c:
        assert c.get("/api/health").json()["status"] == "degraded"
        assert c.get("/api/stations").status_code == 503
