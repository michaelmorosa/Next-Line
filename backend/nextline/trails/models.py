import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Difficulty(models.TextChoices):
    UNRATED = 'unrated', 'Unrated'
    GREEN = 'green', 'Green'
    BLUE = 'blue', 'Blue'
    BLACK = 'black', 'Black diamond'
    DOUBLE_BLACK = 'double_black', 'Double black'


# How much a trail's difficulty multiplies points for clean climbs (progression/ride_xp.py), and ranks trails for
# achievements.
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


class TrailSystem(models.Model):
    """A riding area: a set of shared trails whose features form ladders."""
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    location = models.CharField(max_length=120, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    description = models.TextField(blank=True)
    # Demo data is removed with `manage.py seed_features_demo --remove`.
    is_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class TrailQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Shared trails plus the rider's own auto-detected ones."""
        return self.filter(models.Q(owner__isnull=True) | models.Q(owner=user))


class Trail(models.Model):
    """A descent or climb that efforts are timed on.

    Shared trails (owner empty) are added in the admin and belong to a trail system. Auto trails are created per
    rider from descents and climbs they ride (rides/segments.py) and only show in the app once ridden twice, so
    one-offs don't clutter the list.
    """
    name = models.CharField(max_length=120)
    system = models.ForeignKey(TrailSystem, null=True, blank=True, on_delete=models.SET_NULL, related_name='trails')
    direction = models.CharField(max_length=10, choices=Direction.choices, default=Direction.DESCENT)
    # The official rating, if the trail has one.
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


class FeatureType(models.TextChoices):
    DROP = 'drop', 'Drop'
    JUMP = 'jump', 'Jump'
    CORNER = 'corner', 'Corner'
    ROCK_GARDEN = 'rock_garden', 'Rock garden'
    ROOTS = 'roots', 'Roots'
    STEEP = 'steep', 'Steep'
    SKINNY = 'skinny', 'Skinny'
    CLIMB = 'climb', 'Climb'
    OTHER = 'other', 'Other'


class Certification(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    CERTIFIED = 'certified', 'Certified'
    CHANGED = 'changed', 'Changed since graded'
    CLOSED = 'closed', 'Closed'


# Riders see these. Drafts are team-only and closed features are hidden.
LIVE_STATUSES = (Certification.CERTIFIED, Certification.CHANGED)

MIN_GRADE, MAX_GRADE = 1, 10


def is_trail_team(user):
    """The trail team adds, grades and certifies features: superusers and members of the Trail team group."""
    return bool(user and user.is_authenticated and (user.is_superuser or user.has_perm('trails.edit_feature')))


class FeatureQuerySet(models.QuerySet):
    def live(self):
        """What riders see: certified and changed features on shared trails."""
        return self.filter(status__in=LIVE_STATUSES, trail__owner__isnull=True)

    def visible_to(self, user):
        """Riders see live features; the trail team also sees drafts and closed features."""
        return self.all() if is_trail_team(user) else self.live()


class Feature(models.Model):
    """One graded drop, jump, corner... on a real trail. Riders log how it went; features of a type form a ladder.

    Added as a draft by the trail team (often on site from a phone), then certified by a second reviewer. Flagged
    changed or closed when a trail is rebuilt or weather changes it. See README "Certifying features".
    """
    trail = models.ForeignKey(Trail, on_delete=models.CASCADE, related_name='features')
    name = models.CharField(max_length=80)
    type = models.CharField(max_length=20, choices=FeatureType.choices, default=FeatureType.OTHER)
    # 1-10 within its type, per the grading guidelines. Empty only while a draft.
    grade = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(MIN_GRADE), MaxValueValidator(MAX_GRADE)],
    )
    drop_height_m = models.FloatField(null=True, blank=True)
    gap_length_m = models.FloatField(null=True, blank=True)
    steepness_deg = models.FloatField(null=True, blank=True)
    lat = models.FloatField()
    lng = models.FloatField()
    # Riding order on the trail, low to high.
    position = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
    how_to_ride = models.TextField(blank=True)
    what_can_go_wrong = models.TextField(blank=True)
    has_ride_around = models.BooleanField(default=False)
    ride_around_grade = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(MIN_GRADE), MaxValueValidator(MAX_GRADE)],
    )
    ride_around_note = models.CharField(max_length=200, blank=True)
    # Skill ids from progression/content/skills.json, for "Stuck?" tips and strengths.
    skill_tags = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=10, choices=Certification.choices, default=Certification.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    certified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    certified_at = models.DateTimeField(null=True, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    # Made by the app when a feature is captured, so retrying a queued upload can't add it twice.
    client_id = models.UUIDField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = FeatureQuerySet.as_manager()

    class Meta:
        ordering = ['trail', 'position', 'id']
        permissions = [
            ('edit_feature', 'Can add and edit features as the trail team'),
            ('certify_feature', 'Can certify features'),
        ]

    def __str__(self):
        return f'{self.name} ({self.trail})'

    @property
    def is_live(self):
        return self.status in LIVE_STATUSES


class Outcome(models.TextChoices):
    CLEANED = 'cleaned', 'Cleaned it'
    SKETCHY = 'sketchy', 'Rode it, sketchy'
    WALKED = 'walked', 'Walked it'


def log_video_upload_to(log, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'mp4'
    return f'logs/{log.user_id}/{log.client_id}.{ext}'


class FeatureLog(models.Model):
    """How one go at a feature went. Clean counts, first cleans and statuses are all derived from these."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feature_logs')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='logs')
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    # The rider's local date, sent by the app; weekly caps use it.
    ridden_on = models.DateField()
    logged_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)
    video = models.FileField(upload_to=log_video_upload_to, blank=True)
    ride = models.ForeignKey(
        'rides.Ride', null=True, blank=True, on_delete=models.SET_NULL, related_name='feature_logs',
    )
    # The feature's grade when logged, so regrading it later doesn't rewrite history or points.
    grade_at_log = models.PositiveSmallIntegerField(null=True, blank=True)
    client_id = models.UUIDField(default=uuid.uuid4)

    class Meta:
        ordering = ['-ridden_on', '-logged_at', '-id']
        constraints = [models.UniqueConstraint(fields=['user', 'client_id'], name='one_log_per_client_id')]
        indexes = [models.Index(fields=['user', 'feature', 'ridden_on'])]

    def __str__(self):
        return f'{self.user} · {self.feature} · {self.outcome}'


class MediaKind(models.TextChoices):
    APPROACH = 'approach', 'Approach photo'
    FEATURE = 'feature', 'Feature photo'
    EXIT = 'exit', 'Landing or exit photo'
    POV = 'pov', 'POV clip'


PHOTO_KINDS = (MediaKind.APPROACH, MediaKind.FEATURE, MediaKind.EXIT)


def media_upload_to(media, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
    return f'features/{media.feature_id}/{media.client_id}.{ext}'


def thumb_upload_to(media, filename):
    return f'features/{media.feature_id}/{media.client_id}_thumb.jpg'


class FeatureMedia(models.Model):
    """Photos of a feature (approach, the feature, landing or exit) and its POV clip. Public to signed-in riders."""
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='media')
    kind = models.CharField(max_length=10, choices=MediaKind.choices)
    file = models.FileField(upload_to=media_upload_to, max_length=200)
    thumbnail = models.FileField(upload_to=thumb_upload_to, blank=True, max_length=200)
    caption = models.CharField(max_length=200, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    # Made by the app per photo, so a retried upload can't add it twice.
    client_id = models.UUIDField(default=uuid.uuid4, unique=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['position', 'id']
        verbose_name_plural = 'feature media'

    def __str__(self):
        return f'{self.feature} · {self.get_kind_display()}'


class ReportStatus(models.TextChoices):
    OPEN = 'open', 'Open'
    RESOLVED = 'resolved', 'Resolved'
    DISMISSED = 'dismissed', 'Dismissed'


def report_upload_to(report, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
    return f'reports/{report.feature_id}/{uuid.uuid4()}.{ext}'


class FeatureReport(models.Model):
    """A rider saying a feature has changed. Goes to the trail team's review queue; doesn't change the feature."""
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='reports')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    note = models.CharField(max_length=300, blank=True)
    photo = models.FileField(upload_to=report_upload_to, blank=True, max_length=200)
    status = models.CharField(max_length=10, choices=ReportStatus.choices, default=ReportStatus.OPEN)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.feature} · {self.get_status_display()}'


GUIDELINES_FILE = Path(__file__).resolve().parent / 'content' / 'grading_guidelines.md'


class GradingGuidelines(models.Model):
    """The one editable grading document, so grades stay consistent between team members. Edited in the admin;
    starts from content/grading_guidelines.md."""
    body = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = 'grading guidelines'
        verbose_name_plural = 'grading guidelines'

    def __str__(self):
        return 'Grading guidelines'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        doc = cls.objects.filter(pk=1).first()
        if doc is None:
            doc = cls.objects.create(body=GUIDELINES_FILE.read_text(encoding='utf-8'))
        return doc
