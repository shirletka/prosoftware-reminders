from django.contrib import admin, messages
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from .models import Company, Digest, Task
from .templatetags.reminders_extras import due_label, ru_plural


class TaskInline(admin.TabularInline):
    model = Task
    fields = ["title", "assignee_email", "cycle_days", "last_done_on", "status", "due_on"]
    readonly_fields = ["due_on"]
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "task_count"]
    search_fields = ["name"]
    inlines = [TaskInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(task_count=Count("tasks"))

    @admin.display(description="задач", ordering="task_count")
    def task_count(self, obj: Company) -> int:
        return obj.task_count


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "assignee_email", "cycle_days", "last_done_on", "due_on", "deadline", "status"]
    list_filter = ["status", "company"]
    search_fields = ["title", "assignee_email", "company__name"]
    list_select_related = ["company"]
    readonly_fields = ["due_on", "created_on"]
    actions = ["mark_done"]

    @admin.display(description="", ordering="due_on")
    def deadline(self, obj: Task) -> str:
        left = obj.days_left()
        color = "#d92d20" if left < 0 else "#b54708" if left <= 3 else "#667085"
        return format_html('<span style="color:{}">{}</span>', color, due_label(left))

    @admin.action(description="Отметить выполненными сегодня")
    def mark_done(self, request, queryset) -> None:
        today = timezone.localdate()
        tasks = list(queryset)
        for task in tasks:
            task.mark_done(today)
        n = len(tasks)
        self.message_user(
            request,
            f"{n} {ru_plural(n, 'задача отмечена,задачи отмечены,задач отмечено')} выполненными, сроки сдвинуты.",
            messages.SUCCESS,
        )


@admin.register(Digest)
class DigestAdmin(admin.ModelAdmin):
    list_display = ["email", "sent_on", "created_at", "task_count"]
    list_filter = ["sent_on"]
    search_fields = ["email"]
    filter_horizontal = ["tasks"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(task_count=Count("tasks"))

    @admin.display(description="задач", ordering="task_count")
    def task_count(self, obj: Digest) -> int:
        return obj.task_count

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
