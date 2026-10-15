"""The importer's cleaning rules, checked against a hand-made fixture with known defects."""


def halts(tt, number):
    return [(h.station, h.arr, h.dep) for h in tt.trains[number].halts]


def test_pass_through_rows_are_removed(tt):
    # BBB has arrival == departure on 10001, so it is a timing point, not a halt
    assert [h[0] for h in halts(tt, "10001")] == ["AAA", "CCC", "DDD"]


def test_day_offsets_derived_from_clock_not_day_field(tt):
    stops = {h.station: h for h in tt.trains["10002"].halts}
    assert stops["AAA"].dep == 23 * 60
    assert stops["CCC"].arr == 1440 + 60      # 01:00 next day, despite day field saying 1


def test_small_backward_glitch_is_clamped(tt, built):
    stops = {h.station: h for h in tt.trains["10002"].halts}
    assert stops["GGG"].arr >= stops["CCC"].dep          # never earlier than the previous time
    assert stops["GGG"].arr < 2 * 1440                    # and not pushed a whole extra day
    assert built["stats"]["time_glitches_clamped"] >= 1


def test_rows_without_any_time_are_dropped(built, tt):
    assert built["stats"]["rows_without_time_dropped"] == 1
    assert "BBB" not in [h.station for h in tt.trains["10002"].halts]


def test_distances_scaled_to_official_total_and_monotonic(tt):
    for number in ("10001", "10002"):
        kms = [h.km for h in tt.trains[number].halts]
        assert kms[0] == 0
        assert kms[-1] == tt.trains[number].distance_km
        assert kms == sorted(kms)


def test_unusable_trains_are_skipped(tt, built):
    assert "10006" not in tt.trains       # zero distance
    assert built["stats"]["trains_skipped"] == 1


def test_classes_and_running_days(tt):
    assert tt.trains["10005"].classes == ("GN",)
    assert set(tt.trains["10002"].classes) == {"SL", "3A", "2A"}
    weekly = tt.trains["10004"]
    assert weekly.runs_on_known and weekly.running_days_label == "Mon"
    assert tt.trains["10001"].running_days_label == "Not in source data"


def test_name_tidying(tt):
    assert tt.trains["10001"].name == "Alpha Delta Express"
