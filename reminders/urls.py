from django.urls import path

from . import views

urlpatterns = [
    path("", views.upcoming, name="upcoming"),
    path("tasks/<int:pk>/done/", views.mark_done, name="task-done"),
]
