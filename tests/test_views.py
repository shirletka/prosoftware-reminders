import json
import re
from datetime import timedelta

from django.test import Client
from django.urls import reverse

from reminders.models import Company, Task

from .conftest import TODAY


def test_page_needs_login(client, db):
    response = client.get(reverse("upcoming"))

    assert response.status_code == 302
    assert reverse("admin:login") in response.url


def test_expired_session_redirects_the_whole_page_on_htmx_requests(client, db):
    response = client.get(reverse("upcoming"), HTTP_HX_REQUEST="true")

    assert response.status_code == 204
    assert response["HX-Redirect"].startswith(reverse("admin:login"))


def test_full_page_and_fragment_are_cached_separately(admin_client, db):
    assert "HX-Request" in admin_client.get(reverse("upcoming"))["Vary"]


def test_done_button_carries_a_working_csrf_token(admin_user, make_task):
    task = make_task(0)
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    url = reverse("task-done", args=[task.pk])

    page = client.get(reverse("upcoming")).content.decode()
    headers = json.loads(re.search(r"hx-headers='([^']+)'", page).group(1))

    assert client.post(url, HTTP_HX_REQUEST="true").status_code == 403
    assert client.post(url, HTTP_HX_REQUEST="true", HTTP_X_CSRFTOKEN=headers["X-CSRFToken"]).status_code == 200


def test_page_groups_tasks_by_deadline(admin_client, make_task):
    make_task(-1, title="Медкнижки")
    make_task(0, title="Антивирус")
    make_task(2, title="Чистка кофемашины")
    make_task(5, title="Сверка")

    html = admin_client.get(reverse("upcoming")).content.decode()

    assert html.index("Просрочено") < html.index("Медкнижки") < html.index("Сегодня") < html.index("Антивирус")
    assert html.index("Скоро") < html.index("Чистка кофемашины")
    assert "через 2 дня" in html
    assert "Сверка" not in html


def test_htmx_request_gets_only_the_board(admin_client, make_task):
    make_task(0)

    response = admin_client.get(reverse("upcoming"), HTTP_HX_REQUEST="true")

    assert b"<html" not in response.content
    assert "Задача" in response.content.decode()


def test_filters_by_company_and_horizon(admin_client, make_task):
    other = Company.objects.create(name="Кофейня")
    make_task(0, title="Своя")
    make_task(0, title="Чужая", company=other)
    make_task(6, title="Дальняя", company=other)

    html = admin_client.get(reverse("upcoming"), {"company": other.pk, "days": 7}).content.decode()

    assert "Чужая" in html and "Дальняя" in html
    assert "Своя" not in html


def test_garbage_filters_fall_back_to_defaults(admin_client, make_task):
    make_task(0, title="Сегодняшняя")

    response = admin_client.get(reverse("upcoming"), {"company": "x", "days": "abc"})

    assert response.status_code == 200
    assert "Сегодняшняя" in response.content.decode()


def test_done_button_moves_the_task_out_of_the_board(admin_client, make_task):
    task = make_task(-3, title="Поверка весов", cycle=180)

    response = admin_client.post(reverse("task-done", args=[task.pk]), {"days": 3}, HTTP_HX_REQUEST="true")

    html = response.content.decode()
    assert "«Поверка весов» выполнена. Следующий срок 01.05.2027." in html
    assert 'id="task-' not in html
    assert "ничего не горит" in html
    assert Task.objects.get(pk=task.pk).due_on == TODAY + timedelta(days=180)


def test_done_needs_post(admin_client, make_task):
    task = make_task(0)

    assert admin_client.get(reverse("task-done", args=[task.pk])).status_code == 405


def test_admin_action_marks_tasks_done(admin_client, make_task):
    overdue, soon, untouched = make_task(-5, cycle=30), make_task(1, cycle=7), make_task(2)

    response = admin_client.post(
        reverse("admin:reminders_task_changelist"),
        {"action": "mark_done", "_selected_action": [overdue.pk, soon.pk]},
        follow=True,
    )

    assert "2 задачи отмечены выполненными" in response.content.decode()
    overdue.refresh_from_db()
    soon.refresh_from_db()
    untouched.refresh_from_db()
    assert (overdue.last_done_on, overdue.due_on) == (TODAY, TODAY + timedelta(days=30))
    assert soon.due_on == TODAY + timedelta(days=7)
    assert untouched.last_done_on != TODAY


def test_admin_changelist_renders(admin_client, make_task):
    make_task(-1)

    response = admin_client.get(reverse("admin:reminders_task_changelist"))

    assert response.status_code == 200
    assert "просрочено на 1 день" in response.content.decode()
