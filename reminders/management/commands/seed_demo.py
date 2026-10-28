import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from reminders.models import Company, Task

# (company, title, assignee, cycle, days until due; None = never done)
DEMO = [
    ("ТОО «Алатау Сервис»", "Поверка весов на складе", "aigerim@alatau.kz", 180, -2),
    ("ТОО «Алатау Сервис»", "Продление лицензии антивируса", "it@alatau.kz", 365, 0),
    ("ТОО «Алатау Сервис»", "Инструктаж по пожарной безопасности", "aigerim@alatau.kz", 90, 3),
    ("ТОО «Алатау Сервис»", "Сверка с поставщиками", "aigerim@alatau.kz", 30, 12),
    ("ИП «Нурлан Логистик»", "ТО грузовика 777 ABC 02", "nurlan@logistic.kz", 60, 1),
    ("ИП «Нурлан Логистик»", "Замена тахографа", "nurlan@logistic.kz", 730, None),
    ("ИП «Нурлан Логистик»", "Проверка аптечек", "nurlan@logistic.kz", 180, 4),
    ("Кофейня «Бариста»", "Чистка кофемашины", "barista@coffee.kz", 7, 2),
    ("Кофейня «Бариста»", "Медкнижки сотрудников", "barista@coffee.kz", 365, -10),
]


class Command(BaseCommand):
    help = "Demo companies and tasks with deadlines around today, plus an admin user if DEMO_ADMIN_PASSWORD is set."

    def handle(self, *args, **options) -> None:
        today = timezone.localdate()
        if Task.objects.exists():
            self.stdout.write("Demo data already there, skipping")
        else:
            for company_name, title, email, cycle, due_in in DEMO:
                company, _ = Company.objects.get_or_create(name=company_name)
                last_done = None if due_in is None else today + timedelta(days=due_in - cycle)
                Task.objects.create(
                    company=company, title=title, assignee_email=email, cycle_days=cycle, last_done_on=last_done
                )
            Task.objects.create(
                company=Company.objects.get(name="Кофейня «Бариста»"),
                title="Санобработка летней веранды",
                assignee_email="barista@coffee.kz",
                cycle_days=30,
                last_done_on=today - timedelta(days=40),
                status=Task.Status.PAUSED,
            )
            self.stdout.write(self.style.SUCCESS(f"Created {Task.objects.count()} tasks"))

        password = os.environ.get("DEMO_ADMIN_PASSWORD")
        User = get_user_model()
        if password and not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.kz", password)
            self.stdout.write(self.style.SUCCESS("Superuser admin created"))
