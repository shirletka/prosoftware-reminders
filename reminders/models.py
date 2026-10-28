from datetime import date, timedelta

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Company(models.Model):
    name = models.CharField("название", max_length=200, unique=True)

    class Meta:
        verbose_name = "компания"
        verbose_name_plural = "компании"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TaskQuerySet(models.QuerySet):
    def active(self) -> "TaskQuerySet":
        return self.filter(status=Task.Status.ACTIVE)

    def due(self, days_ahead: int, today: date | None = None) -> "TaskQuerySet":
        """Active tasks whose deadline is overdue, today, or within `days_ahead` days (inclusive)."""
        today = today or timezone.localdate()
        return self.active().filter(due_on__lte=today + timedelta(days=days_ahead))


class Task(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активна"
        PAUSED = "paused", "На паузе"

    company = models.ForeignKey(Company, models.CASCADE, related_name="tasks", verbose_name="компания")
    title = models.CharField("название", max_length=200)
    assignee_email = models.EmailField("email ответственного")
    cycle_days = models.PositiveIntegerField("цикл, дней", validators=[MinValueValidator(1)])
    last_done_on = models.DateField(
        "последнее выполнение",
        null=True,
        blank=True,
        help_text="Пусто — задачу ещё ни разу не выполняли, срок наступает сразу.",
    )
    status = models.CharField("статус", max_length=16, choices=Status.choices, default=Status.ACTIVE)
    # Stored so that "due in the next N days" is a plain indexed filter. Recomputed on every save().
    due_on = models.DateField("срок", editable=False, db_index=True)
    created_on = models.DateField("создана", default=timezone.localdate, editable=False)

    objects = TaskQuerySet.as_manager()

    class Meta:
        verbose_name = "задача"
        verbose_name_plural = "задачи"
        ordering = ["due_on", "title"]
        constraints = [models.CheckConstraint(condition=models.Q(cycle_days__gte=1), name="cycle_days_positive")]

    def __str__(self) -> str:
        return f"{self.title} ({self.company})"

    @property
    def next_due_on(self) -> date:
        if self.last_done_on is None:
            return self.created_on
        return self.last_done_on + timedelta(days=self.cycle_days)

    def is_due(self, days_ahead: int = 3, today: date | None = None) -> bool:
        today = today or timezone.localdate()
        return self.status == self.Status.ACTIVE and self.next_due_on <= today + timedelta(days=days_ahead)

    def days_left(self, today: date | None = None) -> int:
        return (self.next_due_on - (today or timezone.localdate())).days

    def mark_done(self, on: date | None = None) -> None:
        self.last_done_on = on or timezone.localdate()
        self.save(update_fields=["last_done_on", "due_on"])

    def save(self, *args, **kwargs) -> None:
        self.assignee_email = self.assignee_email.strip().lower()
        self.due_on = self.next_due_on
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "due_on" not in update_fields:
            kwargs["update_fields"] = {*update_fields, "due_on"}
        super().save(*args, **kwargs)


class Digest(models.Model):
    """One row per recipient per day. The unique constraint is what prevents a second letter."""

    email = models.EmailField()
    sent_on = models.DateField("за дату")
    tasks = models.ManyToManyField(Task, related_name="digests", verbose_name="задачи")
    created_at = models.DateTimeField("отправлен", auto_now_add=True)

    class Meta:
        verbose_name = "дайджест"
        verbose_name_plural = "отправленные дайджесты"
        ordering = ["-sent_on", "email"]
        constraints = [models.UniqueConstraint(fields=["email", "sent_on"], name="one_digest_per_day")]

    def __str__(self) -> str:
        return f"{self.email} за {self.sent_on:%d.%m.%Y}"
