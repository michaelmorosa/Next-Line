from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    # Who gets texted when crash detection fires and the rider doesn't answer "You OK?".
    crash_contact_name = models.CharField(max_length=80, blank=True)
    crash_contact_phone = models.CharField(max_length=20, blank=True)
    crash_alerts_enabled = models.BooleanField(default=True)
