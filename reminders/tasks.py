from datetime import date

from celery import shared_task
from django.utils import timezone

from . import services


@shared_task
def send_due_digests(day: str | None = None) -> int:
    # The date is fixed here and passed down, so a letter retried after midnight
    # is still deduplicated against the day it was meant for.
    today = date.fromisoformat(day) if day else timezone.localdate()
    recipients = services.due_recipients(today)
    for email in recipients:
        send_digest.delay(email, today.isoformat())
    return len(recipients)


# OSError covers SMTPException, refused connections, timeouts and DNS failures alike.
@shared_task(autoretry_for=(OSError,), retry_backoff=60, max_retries=5)
def send_digest(email: str, day: str) -> bool:
    return services.send_digest(email, date.fromisoformat(day))
