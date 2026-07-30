from datetime import datetime, timedelta, timezone

from src.control_tower.freshness import freshness_classification, refresh_attempt_is_stale


NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


def test_freshness_boundaries_and_missing_snapshot_are_explicit():
    assert freshness_classification(None, now=NOW)["state"] == "CRITICALLY_STALE"
    assert freshness_classification(NOW - timedelta(hours=24), now=NOW)["state"] == "CURRENT"
    assert freshness_classification(NOW - timedelta(hours=24, seconds=1), now=NOW)["state"] == "STALE"
    assert freshness_classification(NOW - timedelta(hours=48, seconds=1), now=NOW)["state"] == "CRITICALLY_STALE"


def test_old_refresh_attempt_is_stale_without_mutating_database_state():
    assert refresh_attempt_is_stale(NOW - timedelta(minutes=31), now=NOW)
    assert not refresh_attempt_is_stale(NOW - timedelta(minutes=29), now=NOW)
