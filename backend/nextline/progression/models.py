"""Riders' practice, attempts, masteries and challenges, plus the XP ledger.

Skills themselves aren't in the database: rows refer to a skill by its id in content/skills.json.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class PracticeSession(models.Model):
    """One logged drill session. Sessions over the daily cap are still saved and count toward mastery; they just
    earn no XP."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='practice_sessions')
    skill_id = models.CharField(max_length=40)
    drill_index = models.PositiveSmallIntegerField(null=True, blank=True)  # None = general practice
    # Repeat uploads with the same client_id are ignored, so the app can retry safely.
    client_id = models.UUIDField(default=uuid.uuid4)
    # The rider's local date, sent by the app. Caps, practice days and streaks use it, so an evening session
    # doesn't land on tomorrow in UTC.
    practiced_on = models.DateField()
    logged_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)
    ride = models.ForeignKey('rides.Ride', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-logged_at', '-id']
        constraints = [models.UniqueConstraint(fields=['user', 'client_id'], name='one_session_per_client_id')]
        indexes = [models.Index(fields=['user', 'skill_id', 'practiced_on'])]

    def __str__(self):
        return f'{self.user} · {self.skill_id} · {self.practiced_on}'


def attempt_upload_to(attempt, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'mp4'
    return f'attempts/{attempt.user_id}/{attempt.client_id}.{ext}'


class Attempt(models.Model):
    """A short video of the rider trying a skill. Private: only the rider can watch it."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attempts')
    skill_id = models.CharField(max_length=40)
    video = models.FileField(upload_to=attempt_upload_to)
    duration_s = models.FloatField(null=True, blank=True)
    client_id = models.UUIDField(default=uuid.uuid4)
    practiced_on = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [models.UniqueConstraint(fields=['user', 'client_id'], name='one_attempt_per_client_id')]
        indexes = [models.Index(fields=['user', 'skill_id', 'practiced_on'])]

    def __str__(self):
        return f'{self.user} · {self.skill_id} · attempt {self.created_at:%Y-%m-%d}'


class Mastery(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='masteries')
    skill_id = models.CharField(max_length=40)
    mastered_at = models.DateTimeField(default=timezone.now)
    confirmed_test = models.BooleanField(default=False)
    # Optional, for coaches and teams later. Shown as a badge, never required.
    coach_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-mastered_at']
        verbose_name_plural = 'masteries'
        constraints = [models.UniqueConstraint(fields=['user', 'skill_id'], name='one_mastery_per_skill')]

    def __str__(self):
        return f'{self.user} · {self.skill_id}'


class GoalType(models.TextChoices):
    SESSIONS = 'sessions', 'Log sessions'
    MASTER = 'master', 'Master skills'


class Challenge(models.Model):
    """Seeded from content/challenges.json (manage.py seed_progression), then edited in the admin."""
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    skill_ids = models.JSONField(default=list)
    goal_type = models.CharField(max_length=10, choices=GoalType.choices)
    goal_count = models.PositiveIntegerField()
    starts_on = models.DateField()
    ends_on = models.DateField()  # inclusive

    class Meta:
        ordering = ['ends_on', 'id']

    def __str__(self):
        return self.title


class ChallengeEntry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='challenge_entries')
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='entries')
    joined_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'challenge entries'
        constraints = [models.UniqueConstraint(fields=['user', 'challenge'], name='one_entry_per_challenge')]

    def __str__(self):
        return f'{self.user} · {self.challenge}'


class Reason(models.TextChoices):
    SESSION = 'session', 'Drill session'
    ATTEMPT = 'attempt', 'Attempt video'
    MASTERY = 'mastery', 'Skill mastered'
    CHALLENGE = 'challenge', 'Challenge complete'
    STREAK = 'streak', 'Practice week'
    RIDE = 'ride', 'Ride'
    DESCENT = 'descent', 'Metres descended'
    JUMPS = 'jumps', 'Jumps'
    FEATURE = 'feature', 'Feature cleaned'
    PR = 'pr', 'Trail PR'
    CLEAN_CLIMB = 'clean_climb', 'Clean climb'
    AIR = 'air', 'Biggest air'
    CORRECTION = 'correction', 'Correction'


class LedgerQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError('The XP ledger is append-only. Add a correction entry instead.')

    def delete(self):
        raise TypeError('The XP ledger is append-only. Add a correction entry instead.')


class XPEntry(models.Model):
    """Every XP award, append-only. Totals and levels are always summed from here, never stored.

    `source` names what earned it (e.g. 'session:812', 'streak:2026-W44'), and is unique per rider, so the same
    thing can never pay out twice. Mistakes are fixed with a negative 'correction' entry.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='xp_entries')
    amount = models.IntegerField()
    reason = models.CharField(max_length=12, choices=Reason.choices)
    skill_id = models.CharField(max_length=40, blank=True)
    challenge = models.ForeignKey(Challenge, null=True, blank=True, on_delete=models.PROTECT)
    source = models.CharField(max_length=80)
    rules_version = models.PositiveIntegerField()
    created_at = models.DateTimeField(default=timezone.now)

    objects = LedgerQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'XP entry'
        verbose_name_plural = 'XP ledger'
        constraints = [models.UniqueConstraint(fields=['user', 'source'], name='one_award_per_source')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError('The XP ledger is append-only. Add a correction entry instead.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError('The XP ledger is append-only. Add a correction entry instead.')

    def __str__(self):
        return f'{self.user} {self.amount:+d} {self.reason}'
