from datetime import date

from django.core.management.base import BaseCommand

from reminders.tasks import send_due_digests


class Command(BaseCommand):
    help = "Run the daily digest now, the same task Celery beat runs at 09:00."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--date", type=date.fromisoformat, help="Pretend today is YYYY-MM-DD")

    def handle(self, *args, **options) -> None:
        day = options["date"].isoformat() if options["date"] else None
        result = send_due_digests.delay(day)
        self.stdout.write(f"Queued digest run {result.id}; letters show up in `docker compose logs celery`")
