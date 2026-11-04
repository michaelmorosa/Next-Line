from django.contrib import admin
from django.utils import timezone

from .models import Attempt, Challenge, ChallengeEntry, Mastery, PracticeSession, XPEntry


@admin.register(PracticeSession)
class PracticeSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'skill_id', 'drill_index', 'practiced_on', 'logged_at')
    list_filter = ('skill_id',)
    search_fields = ('user__username', 'skill_id')
    raw_id_fields = ('user', 'ride')


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'skill_id', 'practiced_on', 'duration_s', 'created_at')
    list_filter = ('skill_id',)
    search_fields = ('user__username', 'skill_id')
    raw_id_fields = ('user',)


@admin.register(Mastery)
class MasteryAdmin(admin.ModelAdmin):
    list_display = ('user', 'skill_id', 'mastered_at', 'confirmed_test', 'coach_verified', 'verified_by')
    list_filter = ('coach_verified', 'skill_id')
    search_fields = ('user__username', 'skill_id')
    raw_id_fields = ('user', 'verified_by')
    actions = ['mark_coach_verified']

    @admin.action(description='Mark as coach verified (by me)')
    def mark_coach_verified(self, request, queryset):
        n = queryset.update(coach_verified=True, verified_by=request.user, verified_at=timezone.now())
        self.message_user(request, f'{n} mastery(ies) marked as coach verified.')


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ('title', 'goal_type', 'goal_count', 'starts_on', 'ends_on')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(ChallengeEntry)
class ChallengeEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'challenge', 'joined_at', 'completed_at')
    raw_id_fields = ('user',)


@admin.register(XPEntry)
class XPEntryAdmin(admin.ModelAdmin):
    """Read-only, except adding entries: fix a mistake with a negative 'correction'."""
    list_display = ('user', 'amount', 'reason', 'skill_id', 'source', 'created_at')
    list_filter = ('reason',)
    search_fields = ('user__username', 'source', 'skill_id')
    raw_id_fields = ('user',)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
