from django.apps import AppConfig


class CostControlConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cost_control"

    def ready(self):
        from . import signals  # noqa
