from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Crash alerts', {'fields': ('crash_contact_name', 'crash_contact_phone', 'crash_alerts_enabled')}),
    )
