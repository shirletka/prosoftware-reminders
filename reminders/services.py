import logging
from datetime import date

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string

from .models import Digest, Task

log = logging.getLogger(__name__)


def due_tasks(today: date, days_ahead: int | None = None):
    days_ahead = settings.REMINDER_DAYS_AHEAD if days_ahead is None else days_ahead
    return Task.objects.due(days_ahead, today).select_related("company").order_by("due_on", "company__name", "title")


def due_recipients(today: date) -> list[str]:
    return sorted(set(due_tasks(today).values_list("assignee_email", flat=True)))


def send_digest(email: str, today: date) -> bool:
    """Send `email` one letter with everything due. Returns False if it was already sent today or nothing is due.

    The Digest row is inserted before the letter goes out, in the same transaction. A concurrent run
    blocks on the unique index and then sees the row; if sending fails, the row is rolled back
    and the next retry sends the letter again.
    """
    with transaction.atomic():
        digest, created = Digest.objects.get_or_create(email=email, sent_on=today)
        if not created:
            log.info("digest for %s on %s already sent", email, today)
            return False

        tasks = list(due_tasks(today).filter(assignee_email=email))
        if not tasks:
            transaction.set_rollback(True)
            return False
        digest.tasks.set(tasks)

        groups = {
            "overdue": [t for t in tasks if t.due_on < today],
            "today": [t for t in tasks if t.due_on == today],
            "soon": [t for t in tasks if t.due_on > today],
        }
        context = {"today": today, "groups": groups, "tasks": tasks, "days_ahead": settings.REMINDER_DAYS_AHEAD}
        send_mail(
            subject=render_to_string("reminders/email/subject.txt", context).strip(),
            message=render_to_string("reminders/email/digest.txt", context),
            from_email=None,
            recipient_list=[email],
        )
    log.info("digest for %s on %s sent, tasks: %d", email, today, len(tasks))
    return True
