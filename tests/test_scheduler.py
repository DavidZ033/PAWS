from datetime import datetime

import pytest

from paws.scheduler import FeedingScheduler


def make(tmp_path=None):
    fed = []
    path = str(tmp_path / "schedule.json") if tmp_path else None
    return FeedingScheduler(path, on_feed=lambda portions, entry: fed.append((portions, entry["id"]))), fed


def test_fires_once_at_the_right_minute():
    sched, fed = make()
    entry = sched.add("08:00", portions=2)
    sched.check(datetime(2026, 10, 5, 7, 59, 50))
    assert fed == []
    sched.check(datetime(2026, 10, 5, 8, 0, 5))
    sched.check(datetime(2026, 10, 5, 8, 0, 35))  # same minute, no repeat
    assert fed == [(2, entry["id"])]
    sched.check(datetime(2026, 10, 6, 8, 0, 5))  # next day fires again
    assert len(fed) == 2


def test_respects_days_and_enabled_flag():
    sched, fed = make()
    weekdays = sched.add("12:00", days=[0, 1, 2, 3, 4])
    sched.check(datetime(2026, 10, 10, 12, 0))  # a Saturday
    assert fed == []
    sched.update(weekdays["id"], enabled=False)
    sched.check(datetime(2026, 10, 12, 12, 0))  # a Monday, but disabled
    assert fed == []
    sched.update(weekdays["id"], enabled=True)
    sched.check(datetime(2026, 10, 12, 12, 0))
    assert len(fed) == 1


def test_schedule_survives_restart(tmp_path):
    sched, _ = make(tmp_path)
    sched.add("18:30", portions=3, label="dinner")
    reloaded, _ = make(tmp_path)
    entries = reloaded.list()
    assert len(entries) == 1
    assert entries[0]["time"] == "18:30" and entries[0]["label"] == "dinner"


def test_next_feeding_picks_soonest():
    sched, _ = make()
    sched.add("08:00")
    sched.add("18:00")
    now = datetime(2026, 10, 5, 12, 0)
    assert sched.next_feeding(now)["at"] == "2026-10-05T18:00:00"
    assert sched.next_feeding(datetime(2026, 10, 5, 19, 0))["at"] == "2026-10-06T08:00:00"


def test_next_feeding_skips_to_allowed_day():
    sched, _ = make()
    sched.add("09:00", days=[0])  # Mondays only
    assert sched.next_feeding(datetime(2026, 10, 6, 10, 0))["at"] == "2026-10-12T09:00:00"


@pytest.mark.parametrize("bad", ["8:00", "24:00", "12:60", "noon", ""])
def test_rejects_bad_times(bad):
    sched, _ = make()
    with pytest.raises(ValueError):
        sched.add(bad)


def test_remove():
    sched, _ = make()
    entry = sched.add("08:00")
    assert sched.remove(entry["id"]) is True
    assert sched.remove(entry["id"]) is False
    assert sched.list() == []
