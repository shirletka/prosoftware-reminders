from django import template

register = template.Library()


@register.filter
def ru_plural(n: int, forms: str) -> str:
    """{{ 5|ru_plural:"задача,задачи,задач" }} -> "задач"."""
    one, few, many = forms.split(",")
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


@register.filter
def due_label(days_left: int) -> str:
    if days_left < 0:
        return f"просрочено на {-days_left} {ru_plural(-days_left, 'день,дня,дней')}"
    if days_left == 0:
        return "сегодня"
    if days_left == 1:
        return "завтра"
    return f"через {days_left} {ru_plural(days_left, 'день,дня,дней')}"


@register.filter
def days_left_from(task, today) -> int:
    return task.days_left(today)
