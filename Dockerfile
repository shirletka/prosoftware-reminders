FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.8.0 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/venv PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /srv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY manage.py ./
COPY config ./config
COPY reminders ./reminders

FROM base AS test
RUN uv sync --frozen --no-install-project
COPY tests ./tests
CMD ["pytest", "-v"]

FROM base AS runtime
RUN DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput -v 0
RUN useradd --system --create-home app
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
