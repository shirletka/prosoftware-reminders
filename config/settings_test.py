import os

os.environ.setdefault("DJANGO_SECRET_KEY", "tests-only")

from .settings import *  # noqa: E402, F403
