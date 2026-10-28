from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine

from config import celery_app
from reminders.models import Company, Task

TODAY = date(2026, 11, 2)


@pytest.fixture(autouse=True)
def frozen_clock():
    with time_machine.travel(datetime(2026, 11, 2, 10, 0, tzinfo=ZoneInfo("Asia/Almaty")), tick=False) as traveller:
        yield traveller


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


@pytest.fixture
def company(db) -> Company:
    return Company.objects.create(name="ТОО «Тест»")


@pytest.fixture
def make_task(company):
    def make(due_in: int | None = 0, *, cycle: int = 30, email: str = "a@example.kz", title: str = "Задача", **extra):
        """A task whose deadline is `due_in` days from TODAY (None: never done)."""
        last_done = None if due_in is None else TODAY + timedelta(days=due_in - cycle)
        return Task.objects.create(
            company=extra.pop("company", company),
            title=title,
            assignee_email=email,
            cycle_days=cycle,
            last_done_on=last_done,
            **extra,
        )

    return make
