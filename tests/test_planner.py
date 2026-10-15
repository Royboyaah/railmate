"""Journey search, connections, running days, fares and scoring."""

from app.services.fares import estimate_fare
from app.services.planner import build_journey, find_direct, plan
from tests.conftest import next_weekday

MON, TUE = next_weekday(0), next_weekday(1)


def numbers(journeys):
    return [tuple(leg.train.number for leg in j.legs) for j in journeys]


def test_direct_search_finds_trains_in_order_only(tt):
    assert ("10001",) in numbers(find_direct(tt, "AAA", "DDD", TUE, "SL"))
    assert find_direct(tt, "DDD", "AAA", TUE, "SL") == []          # wrong direction


def test_running_days_are_enforced(tt):
    assert ("10004",) in numbers(find_direct(tt, "AAA", "DDD", MON, "SL"))
    assert ("10004",) not in numbers(find_direct(tt, "AAA", "DDD", TUE, "SL"))


def test_class_filter(tt):
    assert find_direct(tt, "CCC", "DDD", TUE, "GN")                 # passenger train
    assert ("10005",) not in numbers(find_direct(tt, "CCC", "DDD", TUE, "SL"))


def test_connection_found_with_valid_layover(tt, model):
    journeys = plan(tt, model, "AAA", "FFF", TUE, "SL", "balanced")
    transfers = [j for j in journeys if len(j.legs) == 2]
    assert transfers, "expected a connection via DDD"
    j = transfers[0]
    assert j.legs[0].alight.station == "DDD" == j.legs[1].board.station
    assert 45 <= j.layover <= 360
    assert j.legs[1].start >= j.legs[0].end + 45
    assert 0 <= j.connection_risk <= 1


def test_connections_can_be_disabled(tt, model):
    assert plan(tt, model, "AAA", "FFF", TUE, "SL", "balanced", include_transfers=False) == []


def test_scores_are_absolute_and_bounded(tt, model):
    for priority in ("balanced", "fastest", "cheapest", "reliable"):
        for j in plan(tt, model, "AAA", "DDD", MON, "SL", priority):
            for key in ("total", "speed", "cost", "reliability", "convenience"):
                assert 0 <= j.scores[key] <= 100
            assert 0 <= j.scores["p_late"] <= 1


def test_build_journey_rejects_tampering(tt, model):
    import pytest
    with pytest.raises(ValueError, match="does not run from"):
        build_journey(tt, model, [("10001", "DDD", "AAA")], TUE, "SL")
    with pytest.raises(ValueError, match="no 2A"):
        build_journey(tt, model, [("10001", "AAA", "DDD")], TUE, "2A")
    with pytest.raises(ValueError, match="selected date"):
        build_journey(tt, model, [("10004", "AAA", "DDD")], TUE, "SL")
    with pytest.raises(ValueError, match="must start where"):
        build_journey(tt, model, [("10001", "AAA", "CCC"), ("10003", "DDD", "FFF")], TUE, "SL")


def test_fare_model_properties():
    assert estimate_fare(100, "SL") == estimate_fare(200, "SL")            # minimum chargeable distance
    assert estimate_fare(800, "3A") > estimate_fare(800, "SL")
    assert estimate_fare(800, "3A", "Superfast") > estimate_fare(800, "3A", "Express")
    assert estimate_fare(2000, "SL") / 2000 < estimate_fare(400, "SL") / 400   # tapering
    assert estimate_fare(500, "SL") % 5 == 0
