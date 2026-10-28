from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from reminders.models import Task

from .conftest import TODAY


@pytest.mark.parametrize(
    ("due_in", "expected"),
    [
        (-30, True),  # long overdue
        (-1, True),  # overdue since yesterday
        (0, True),  # due today
        (1, True),
        (3, True),  # exactly at the horizon: included
        (4, False),  # one day past the horizon
        (90, False),
    ],
)
def test_is_due_around_the_boundaries(make_task, due_in, expected):
    assert make_task(due_in).is_due(days_ahead=3, today=TODAY) is expected


def test_zero_days_ahead_means_today_and_overdue_only(make_task):
    assert make_task(0).is_due(days_ahead=0, today=TODAY)
    assert make_task(-5).is_due(days_ahead=0, today=TODAY)
    assert not make_task(1).is_due(days_ahead=0, today=TODAY)


def test_never_done_task_is_due_right_away(make_task):
    task = make_task(None, cycle=365)

    assert task.due_on == TODAY
    assert task.is_due(today=TODAY)


def test_paused_task_is_never_due(make_task):
    assert not make_task(-10, status=Task.Status.PAUSED).is_due(today=TODAY)


def test_database_filter_agrees_with_is_due(make_task):
    tasks = [make_task(d, title=f"d{d}") for d in range(-5, 10)] + [make_task(-1, status=Task.Status.PAUSED)]

    expected = {t.pk for t in tasks if t.is_due(days_ahead=3, today=TODAY)}

    assert set(Task.objects.due(3, TODAY).values_list("pk", flat=True)) == expected


def test_mark_done_moves_the_deadline_by_one_cycle(make_task):
    task = make_task(-2, cycle=30)

    task.mark_done(TODAY)
    task.refresh_from_db()

    assert task.last_done_on == TODAY
    assert task.due_on == TODAY + timedelta(days=30)
    assert not task.is_due(today=TODAY)


def test_early_completion_counts_the_cycle_from_the_actual_date(make_task):
    task = make_task(2, cycle=7)

    task.mark_done(TODAY)

    assert task.due_on == TODAY + timedelta(days=7)


def test_editing_the_cycle_recomputes_the_deadline(make_task):
    task = make_task(10, cycle=30)

    task.cycle_days = 18
    task.save()

    assert Task.objects.get(pk=task.pk).due_on == TODAY - timedelta(days=2)


def test_assignee_email_is_normalized(make_task):
    assert make_task(email="  Aigerim@Example.KZ ").assignee_email == "aigerim@example.kz"


def test_today_is_the_local_date_in_almaty(make_task, frozen_clock):
    task = make_task(3)  # due on 05.11

    # 01.11 19:30 UTC is already 02.11 in Almaty: 05.11 is within 3 days.
    frozen_clock.move_to(datetime(2026, 11, 1, 19, 30, tzinfo=ZoneInfo("UTC")))
    assert task.is_due()

    # 01.11 17:00 UTC is still 01.11 in Almaty: 05.11 is four days away.
    frozen_clock.move_to(datetime(2026, 11, 1, 17, 0, tzinfo=ZoneInfo("UTC")))
    assert not task.is_due()
