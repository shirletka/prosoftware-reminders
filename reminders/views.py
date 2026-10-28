from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, render, resolve_url
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_GET, require_POST

from . import services
from .models import Company, Task

DAY_OPTIONS = (0, 3, 7, 14, 30)


def staff_page(view):
    """login_required that also works for htmx: a plain 302 would swap the login page into #board."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.headers.get("HX-Request") and not request.user.is_authenticated:
            response = HttpResponse(status=204)
            query = urlencode({"next": reverse("upcoming")})
            response["HX-Redirect"] = f"{resolve_url(settings.LOGIN_URL)}?{query}"
            return response
        return login_required(view)(request, *args, **kwargs)

    return wrapper


def _board_context(params: QueryDict) -> dict:
    today = timezone.localdate()
    try:
        days = int(params.get("days", settings.REMINDER_DAYS_AHEAD))
    except ValueError:
        days = settings.REMINDER_DAYS_AHEAD
    days = min(max(days, 0), max(DAY_OPTIONS))
    company = params.get("company", "")

    tasks = services.due_tasks(today, days)
    if company.isdigit():
        tasks = tasks.filter(company_id=int(company))
    tasks = list(tasks)

    return {
        "today": today,
        "days": days,
        "day_options": sorted({*DAY_OPTIONS, days}),
        "company": company,
        "companies": Company.objects.all(),
        "total": len(tasks),
        "sections": [
            ("overdue", "Просрочено", [t for t in tasks if t.due_on < today]),
            ("today", "Сегодня", [t for t in tasks if t.due_on == today]),
            ("soon", "Скоро", [t for t in tasks if t.due_on > today]),
        ],
    }


@staff_page
@require_GET
def upcoming(request: HttpRequest) -> HttpResponse:
    context = _board_context(request.GET)
    partial = request.headers.get("HX-Request") and not request.headers.get("HX-History-Restore-Request")
    template = "reminders/_board.html" if partial else "reminders/upcoming.html"
    response = render(request, template, context)
    # The same URL returns a fragment or a full page, caches must keep them apart.
    patch_vary_headers(response, ["HX-Request"])
    return response


@staff_page
@require_POST
def mark_done(request: HttpRequest, pk: int) -> HttpResponse:
    task = get_object_or_404(Task, pk=pk)
    task.mark_done()
    context = _board_context(request.POST)
    context["done"] = task
    return render(request, "reminders/_board.html", context)
