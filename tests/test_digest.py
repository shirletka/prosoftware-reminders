import threading
from datetime import datetime, timedelta
from smtplib import SMTPServerDisconnected
from zoneinfo import ZoneInfo

import pytest
from django.db import connection

from config import celery_app
from reminders import services
from reminders.models import Digest, Task
from reminders.tasks import send_digest, send_due_digests

from .conftest import TODAY


def letter_to(mailoutbox, email):
    [letter] = [m for m in mailoutbox if m.to == [email]]
    return letter


def test_each_assignee_gets_one_letter_with_all_their_tasks(make_task, mailoutbox):
    make_task(-2, title="Поверка весов", email="aigerim@example.kz")
    make_task(0, title="Лицензия антивируса", email="aigerim@example.kz")
    make_task(3, title="Инструктаж", email="aigerim@example.kz")
    make_task(4, title="Сверка с поставщиками", email="aigerim@example.kz")
    make_task(1, title="ТО грузовика", email="nurlan@example.kz")

    assert send_due_digests.delay(TODAY.isoformat()).get() == 2

    assert len(mailoutbox) == 2
    letter = letter_to(mailoutbox, "aigerim@example.kz")
    assert letter.subject == "Сроки на 02.11: 3 задачи, просрочено 1"
    assert "Поверка весов" in letter.body
    assert "просрочено на 2 дня" in letter.body
    assert "Лицензия антивируса" in letter.body
    assert "Инструктаж" in letter.body
    assert "Сверка с поставщиками" not in letter.body
    assert "ТО грузовика" in letter_to(mailoutbox, "nurlan@example.kz").body


def test_running_twice_on_the_same_day_sends_nothing_new(make_task, mailoutbox):
    make_task(0)

    send_due_digests(TODAY.isoformat())
    send_due_digests(TODAY.isoformat())

    assert len(mailoutbox) == 1
    assert Digest.objects.count() == 1


def test_next_day_sends_again(make_task, mailoutbox):
    make_task(0)

    send_due_digests(TODAY.isoformat())
    send_due_digests((TODAY + timedelta(days=1)).isoformat())

    assert len(mailoutbox) == 2


def test_default_day_is_today_in_almaty(make_task, mailoutbox, frozen_clock):
    make_task(3)
    # 02:00 in Almaty is still the previous day in UTC: with a UTC date the task would be 4 days away.
    frozen_clock.move_to(datetime(2026, 11, 2, 2, 0, tzinfo=ZoneInfo("Asia/Almaty")))

    send_due_digests()

    assert Digest.objects.get().sent_on == TODAY
    assert len(mailoutbox) == 1


def test_nothing_due_means_no_letters(make_task, mailoutbox):
    make_task(4)
    make_task(-3, status=Task.Status.PAUSED)

    assert send_due_digests(TODAY.isoformat()) == 0
    assert mailoutbox == []


def test_email_case_does_not_split_the_digest(make_task, mailoutbox):
    make_task(0, email="Aigerim@Example.kz")
    make_task(1, email="aigerim@example.kz")

    send_due_digests(TODAY.isoformat())

    assert len(mailoutbox) == 1


def test_digest_remembers_what_was_sent(make_task):
    due = [make_task(0, title="a"), make_task(2, title="b")]
    make_task(10, title="c")

    services.send_digest("a@example.kz", TODAY)

    assert set(Digest.objects.get().tasks.all()) == set(due)


def test_failed_send_is_not_recorded_so_the_retry_goes_out(make_task, mailoutbox, monkeypatch):
    make_task(0)
    real_send_mail = services.send_mail
    calls = []

    def flaky_send_mail(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise SMTPServerDisconnected("connection dropped")
        return real_send_mail(*args, **kwargs)

    monkeypatch.setattr(services, "send_mail", flaky_send_mail)

    with pytest.raises(SMTPServerDisconnected):
        services.send_digest("a@example.kz", TODAY)
    assert Digest.objects.count() == 0

    assert services.send_digest("a@example.kz", TODAY)
    assert len(mailoutbox) == 1


def test_celery_retries_when_the_mail_server_is_unreachable(make_task, mailoutbox, monkeypatch):
    make_task(0)
    real_send_mail = services.send_mail
    failures = [TimeoutError("timed out"), ConnectionRefusedError("refused")]

    def flaky_send_mail(*args, **kwargs):
        if failures:
            raise failures.pop(0)
        return real_send_mail(*args, **kwargs)

    monkeypatch.setattr(services, "send_mail", flaky_send_mail)
    # Eager Celery runs each retry inline right away (no backoff) and then reports the first call as RETRY.
    celery_app.conf.task_eager_propagates = False  # the autouse fixture turns it back on for the next test

    send_digest.apply(args=["a@example.kz", TODAY.isoformat()])

    assert failures == []
    assert len(mailoutbox) == 1
    assert Digest.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_parallel_runs_send_one_letter(make_task, mailoutbox):
    if connection.vendor != "postgresql":
        pytest.skip("needs real row locking, runs in docker compose against Postgres")
    make_task(0)
    barrier = threading.Barrier(4)
    results = []

    def run():
        barrier.wait()
        try:
            results.append(services.send_digest("a@example.kz", TODAY))
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [False, False, False, True]
    assert len(mailoutbox) == 1
