from django.apps import AppConfig
from django.core import checks


class ProgressionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'progression'

    def ready(self):
        checks.register(check_content)


def check_content(app_configs, **kwargs):
    """Bad skill or rules content stops `check`, `migrate`, `runserver` and `test`, instead of serving a broken tree."""
    from .content import validate
    errors, _ = validate()
    return [checks.Error(e, hint='Run `python manage.py validate_progression`.', id='progression.E001') for e in errors]
