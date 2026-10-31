from django.contrib import admin

from .models import Achievement, CrashAlert, Jump, Ride, TrailEffort


class JumpInline(admin.TabularInline):
    model = Jump
    extra = 0


class EffortInline(admin.TabularInline):
    model = TrailEffort
    extra = 0
    raw_id_fields = ('trail', 'user')


@admin.register(Ride)
class RideAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'started_at', 'distance_m', 'descent_m', 'jump_count', 'flow_score')
    search_fields = ('user__username', 'title')
    raw_id_fields = ('user',)
    exclude = ('track',)
    inlines = [EffortInline, JumpInline]


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('user', 'key', 'earned_at')
    list_filter = ('key',)
    raw_id_fields = ('user',)


@admin.register(CrashAlert)
class CrashAlertAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'contact_phone', 'lat', 'lng', 'created_at')
    list_filter = ('status',)
    raw_id_fields = ('user',)
