from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    # Who gets texted when crash detection fires and the rider doesn't answer "You OK?".
    crash_contact_name = models.CharField(max_length=80, blank=True)
    crash_contact_phone = models.CharField(max_length=20, blank=True)
    crash_alerts_enabled = models.BooleanField(default=True)
    # Suggestions above the advanced grade (rules.json next_up.advanced_above_grade) only when turned on.
    advanced_features = models.BooleanField(default=False)
    # When the rider accepted the safety notice, and which version (trails/content/safety.md).
    safety_accepted_at = models.DateTimeField(null=True, blank=True)
    safety_version = models.PositiveSmallIntegerField(default=0)
