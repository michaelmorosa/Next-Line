"""API error responses."""
import math

from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """DRF's default, except rate limits read "Too many requests. Please try again in about 12 minutes."

    The app shows this text as-is, so it should make sense to a person, not "Request was throttled".
    """
    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, Throttled):
        wait = exc.wait
        if wait is None:
            when = 'later'
        elif wait < 60:
            when = 'in a minute'
        elif wait < 3600:
            minutes = math.ceil(wait / 60)
            when = f'in about {minutes} minute{"s" if minutes != 1 else ""}'
        else:
            hours = math.ceil(wait / 3600)
            when = f'in about {hours} hour{"s" if hours != 1 else ""}'
        response.data = {'detail': f'Too many requests. Please try again {when}.'}
    return response
