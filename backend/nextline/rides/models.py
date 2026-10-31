from django.conf import settings
from django.db import models

from trails.models import Trail


class Ride(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='rides')
    # Made by the app when recording starts, so retrying an upload after a dropped connection can't save it twice.
    client_id = models.UUIDField()
    title = models.CharField(max_length=120, blank=True)
    started_at = models.DateTimeField()
    elapsed_s = models.FloatField()
    # Time spent moving; stops (snack, regroup, fixing a flat) are left out, like auto-pause.
    moving_s = models.FloatField(default=0)
    distance_m = models.FloatField(default=0)
    climb_m = models.FloatField(default=0)
    descent_m = models.FloatField(default=0)
    max_speed = models.FloatField(default=0)  # m/s
    # [[seconds since start, lat, lng, altitude m, speed m/s], ...] after downsampling.
    track = models.JSONField(default=list, blank=True)

    jump_count = models.PositiveIntegerField(default=0)
    total_air_s = models.FloatField(default=0)
    biggest_air_s = models.FloatField(default=0)
    # 0-100 speed steadiness on descents; empty when the ride had no descent long enough to score.
    flow_score = models.FloatField(null=True, blank=True)
    # Feet put down on descents, estimated from stalls (rides/analysis.find_touchdowns). The rider can correct it
    # in the check-in, which sets `touchdowns`.
    touchdowns_detected = models.PositiveIntegerField(default=0)

    # Climbing. Time and climb rate (vertical m/hour) cover the detected climbs only, so flat riding and stops
    # between climbs don't count against them.
    climb_time_s = models.FloatField(default=0)
    descent_time_s = models.FloatField(default=0)
    climb_rate = models.PositiveIntegerField(null=True, blank=True)
    # Stamina: most vertical gained without a rest (a stop of 15 s or more), the number of rests on climbs, and the
    # climb rate in the second half of the ride's climbing as a % of the first half (100 = held pace).
    longest_nonstop_climb_m = models.FloatField(default=0)
    climb_rests = models.PositiveIntegerField(default=0)
    climb_pace_held = models.PositiveIntegerField(null=True, blank=True)

    # Post-ride check-in.
    confidence = models.PositiveSmallIntegerField(null=True, blank=True)
    crashed = models.BooleanField(default=False)
    touchdowns = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # Feature ids marked cleaned in this ride's check-in. Kept so editing the check-in adjusts clean counts
    # instead of adding to them again.
    cleaned_features = models.JSONField(default=list, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-started_at']
        constraints = [models.UniqueConstraint(fields=['user', 'client_id'], name='one_upload_per_recording')]

    def __str__(self):
        return f'{self.user} · {self.title or self.started_at:%Y-%m-%d}'

    @property
    def touchdown_count(self):
        """The rider's own count if they gave one, otherwise the estimate."""
        return self.touchdowns if self.touchdowns is not None else self.touchdowns_detected


class Jump(models.Model):
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name='jumps')
    t = models.FloatField()  # seconds since ride start
    airtime_s = models.FloatField()
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['t']


class TrailEffort(models.Model):
    """One timed run down a trail during a ride."""
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name='efforts')
    trail = models.ForeignKey(Trail, on_delete=models.CASCADE, related_name='efforts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='efforts')
    start_t = models.FloatField()
    elapsed_s = models.FloatField()
    avg_speed = models.FloatField()
    flow_score = models.FloatField(null=True, blank=True)
    # Beat every earlier effort by this rider on this trail. A first run is never a PR.
    is_pr = models.BooleanField(default=False)
    # Estimated feet down during this lap; 0 is a clean lap.
    touchdowns = models.PositiveIntegerField(default=0)
    # Climbs only: vertical metres per hour on this lap.
    climb_rate = models.PositiveIntegerField(null=True, blank=True)
    started_at = models.DateTimeField()

    class Meta:
        ordering = ['started_at']


class CrashAlert(models.Model):
    class Status(models.TextChoices):
        SENT = 'sent', 'Text sent'
        NOT_CONFIGURED = 'not_configured', 'Texting not set up'
        NO_CONTACT = 'no_contact', 'No contact set'
        FAILED = 'failed', 'Send failed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='crash_alerts')
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Achievement(models.Model):
    """A one-off milestone a rider has earned. The list of milestones is in rides/achievements.py."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='achievements')
    key = models.CharField(max_length=40)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['earned_at']
        constraints = [models.UniqueConstraint(fields=['user', 'key'], name='one_of_each_achievement')]

    def __str__(self):
        return f'{self.user} · {self.key}'
