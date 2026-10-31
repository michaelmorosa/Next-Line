"""Crash alert texts through Twilio's REST API (no SDK needed)."""
import base64
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from .models import CrashAlert

logger = logging.getLogger(__name__)

TWILIO_URL = 'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json'


def texting_configured():
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER)


def alert_message(user, lat, lng):
    name = user.first_name or user.username
    where = f' Last location: https://maps.google.com/?q={lat:.6f},{lng:.6f}' if lat is not None and lng is not None else ''
    return (
        f'Next Line crash alert: {name} may have crashed while riding and did not respond to a check.{where} '
        f'Try calling them.'
    )


def send_text(to, body):
    sid = settings.TWILIO_ACCOUNT_SID
    data = urllib.parse.urlencode({'To': to, 'From': settings.TWILIO_FROM_NUMBER, 'Body': body}).encode()
    request = urllib.request.Request(TWILIO_URL.format(sid=sid), data=data, method='POST')
    token = base64.b64encode(f'{sid}:{settings.TWILIO_AUTH_TOKEN}'.encode()).decode()
    request.add_header('Authorization', f'Basic {token}')
    with urllib.request.urlopen(request, timeout=10) as response:
        return 200 <= response.status < 300


def send_crash_alert(user, lat=None, lng=None):
    phone = user.crash_contact_phone
    if not phone or not user.crash_alerts_enabled:
        status = CrashAlert.Status.NO_CONTACT
    elif not texting_configured():
        logger.warning('Crash alert for user %s not texted: Twilio is not configured.', user.pk)
        status = CrashAlert.Status.NOT_CONFIGURED
    else:
        try:
            status = CrashAlert.Status.SENT if send_text(phone, alert_message(user, lat, lng)) else CrashAlert.Status.FAILED
        except (urllib.error.URLError, OSError):
            logger.exception('Crash alert text for user %s failed.', user.pk)
            status = CrashAlert.Status.FAILED
    return CrashAlert.objects.create(user=user, lat=lat, lng=lng, contact_phone=phone, status=status)
