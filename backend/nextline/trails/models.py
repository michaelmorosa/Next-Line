from django.conf import settings
from django.db import models


class Difficulty(models.TextChoices):
    UNRATED = 'unrated', 'Unrated'
    GREEN = 'green', 'Green'
    BLUE = 'blue', 'Blue'
    BLACK = 'black', 'Black diamond'
    DOUBLE_BLACK = 'double_black', 'Double black'


# How much a trail's difficulty counts toward rider level (rides/scoring.py).
DIFFICULTY_WEIGHT = {
    Difficulty.UNRATED: 1.0,
    Difficulty.GREEN: 1.0,
    Difficulty.BLUE: 2.0,
    Difficulty.BLACK: 4.0,
    Difficulty.DOUBLE_BLACK: 6.0,
}


# Riders rate the trails they discovered themselves, so for rider level their rating counts up to this at most.
# Black and double-black need a shared trail, rated in the admin.
RIDER_RATED_MAX = Difficulty.BLUE


def trusted_difficulty(difficulty, owner_id):
    """The difficulty rider level uses: a rider's own rating is capped at RIDER_RATED_MAX."""
    if owner_id and DIFFICULTY_WEIGHT.get(difficulty, 1.0) > DIFFICULTY_WEIGHT[RIDER_RATED_MAX]:
        return RIDER_RATED_MAX
    return difficulty


def trusted_weight(difficulty, owner_id):
    return DIFFICULTY_WEIGHT.get(trusted_difficulty(difficulty, owner_id), 1.0)


class Direction(models.TextChoices):
    DESCENT = 'descent', 'Descent'
    CLIMB = 'climb', 'Climb'


class TrailQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Shared trails plus the rider's own auto-detected ones."""
        return self.filter(models.Q(owner__isnull=True) | models.Q(owner=user))


class Trail(models.Model):
    """A descent or climb that efforts are timed on.

    Shared trails (owner empty) are added in the admin. Auto trails are created per rider from descents and climbs
    they ride (rides/segments.py) and only show in the app once ridden twice, so one-offs don't clutter the list.
    """
    name = models.CharField(max_length=120)
    direction = models.CharField(max_length=10, choices=Direction.choices, default=Direction.DESCENT)
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, default=Difficulty.UNRATED)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name='own_trails',
    )
    is_auto = models.BooleanField(default=False)
    start_lat = models.FloatField()
    start_lng = models.FloatField()
    end_lat = models.FloatField()
    end_lng = models.FloatField()
    length_m = models.FloatField()
    # Elevation change start to finish, always positive: the drop for a descent, the gain for a climb.
    drop_m = models.FloatField(default=0)
    # Simplified [[lat, lng], ...] for drawing; matching only uses the endpoints and length.
    path = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TrailQuerySet.as_manager()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class FeatureKind(models.TextChoices):
    DROP = 'drop', 'Drop'
    JUMP = 'jump', 'Jump'
    GAP = 'gap', 'Gap'
    ROCK_GARDEN = 'rock_garden', 'Rock garden'
    ROOTS = 'roots', 'Roots'
    BERM = 'berm', 'Berm'
    TECHNICAL = 'technical', 'Technical move'
    OTHER = 'other', 'Other'


class FeatureQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Approved features on trails the rider can see, plus the rider's own pins still waiting for approval."""
        return self.filter(trail__in=Trail.objects.visible_to(user)).filter(
            models.Q(approved=True) | models.Q(created_by=user)
        )


class Feature(models.Model):
    """A drop, jump, rock garden... pinned on a trail, to check off over future rides.

    Pins on a shared trail by riders wait for approval in the admin: until then only the rider who pinned it sees
    it, and it doesn't count toward rider level. Pins on a rider's own trail, and by staff, are approved at once.
    """
    trail = models.ForeignKey(Trail, on_delete=models.CASCADE, related_name='features')
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=20, choices=FeatureKind.choices, default=FeatureKind.OTHER)
    lat = models.FloatField()
    lng = models.FloatField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = FeatureQuerySet.as_manager()

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.name} ({self.trail})'


class FeatureStatus(models.TextChoices):
    LOCKED = 'locked', 'Locked'
    ALMOST = 'almost', 'Almost'
    CLEANED = 'cleaned', 'Cleaned'


class FeatureProgress(models.Model):
    """One rider's progress on one feature. No row means locked."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feature_progress')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='progress')
    status = models.CharField(max_length=10, choices=FeatureStatus.choices, default=FeatureStatus.LOCKED)
    clean_count = models.PositiveIntegerField(default=0)
    first_cleaned_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=120, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'feature'], name='one_progress_per_feature')]

    def __str__(self):
        return f'{self.user} · {self.feature} · {self.status}'
