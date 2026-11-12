"""The trail team's workflow: add a draft on site, submit it, certify it with a second reviewer, flag changes.

Draft -> submitted for review -> certified (by someone other than who added or submitted it, when
rules.json verification.second_reviewer_required is on) -> changed or closed -> re-certified or closed.
"""
import io
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from progression import content
from rides.analysis import haversine

from .models import (
    PHOTO_KINDS, Certification, Feature, FeatureMedia, FeatureReport, ReportStatus, Trail, is_trail_team,
)

# A capture belongs to the nearest shared trail within this distance of its GPS point.
NEAREST_TRAIL_M = 150
PHOTO_LONG_EDGE = 2048
THUMB_LONG_EDGE = 640
DAYS_PER_MONTH = 30.44


class CertificationError(Exception):
    pass


def can_certify(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.has_perm('trails.certify_feature')))


def second_reviewer_required():
    return content.rules()['verification']['second_reviewer_required']


def stale_after():
    return timedelta(days=round(content.rules()['verification']['stale_after_months'] * DAYS_PER_MONTH))


def is_stale(feature, now=None):
    """A live feature nobody on the team has checked within the verification window."""
    if not feature.is_live:
        return False
    checked = feature.last_verified_at or feature.certified_at
    return checked is None or (now or timezone.now()) - checked > stale_after()


def stale_features(now=None):
    cutoff = (now or timezone.now()) - stale_after()
    return Feature.objects.live().filter(Q(last_verified_at__lt=cutoff) | Q(last_verified_at__isnull=True))


# Where a feature sits along its trail.

def path_of(trail):
    return trail.path or [[trail.start_lat, trail.start_lng], [trail.end_lat, trail.end_lng]]


def nearest_vertex(trail, lat, lng):
    """(index of the nearest path point, distance in metres)."""
    return min(((i, haversine(lat, lng, p[0], p[1])) for i, p in enumerate(path_of(trail))), key=lambda x: x[1])


def nearest_trail(lat, lng, max_m=NEAREST_TRAIL_M):
    """The shared trail whose line passes closest to a point, or None if none is within max_m."""
    d = 0.02  # about 2 km, to narrow the search
    candidates = Trail.objects.filter(
        owner__isnull=True, start_lat__range=(lat - d * 5, lat + d * 5), start_lng__range=(lng - d * 5, lng + d * 5),
    )
    best = min(((t, nearest_vertex(t, lat, lng)[1]) for t in candidates), key=lambda x: x[1], default=None)
    return best[0] if best and best[1] <= max_m else None


def place_on_trail(feature):
    """Put a new feature in riding order by where its GPS point falls along the trail, renumbering the others."""
    trail = feature.trail
    index = nearest_vertex(trail, feature.lat, feature.lng)[0]
    others = list(trail.features.exclude(pk=feature.pk).order_by('position', 'id'))
    # Before the first feature further down the trail, so a manual reorder of the others is kept.
    insert_at = next((i for i, f in enumerate(others) if nearest_vertex(trail, f.lat, f.lng)[0] > index), len(others))
    ordered = others[:insert_at] + [feature] + others[insert_at:]
    for position, f in enumerate(ordered, start=1):
        if f is feature:
            feature.position = position
        elif f.position != position:
            Feature.objects.filter(pk=f.pk).update(position=position)


def renumber(trail, ordered_ids):
    """Set the riding order of a trail's features from a list of ids (the bulk trail view)."""
    with transaction.atomic():
        for position, feature_id in enumerate(ordered_ids, start=1):
            Feature.objects.filter(pk=feature_id, trail=trail).update(position=position)


# Media.

def process_photo(upload):
    """(full-size JPEG, thumbnail JPEG) as ContentFiles: the long edge cut to PHOTO_LONG_EDGE, EXIF rotation applied
    so the photo is upright, and location data dropped."""
    from PIL import Image, ImageOps

    image = Image.open(upload)
    image = ImageOps.exif_transpose(image).convert('RGB')
    full = image.copy()
    full.thumbnail((PHOTO_LONG_EDGE, PHOTO_LONG_EDGE))
    thumb = image.copy()
    thumb.thumbnail((THUMB_LONG_EDGE, THUMB_LONG_EDGE))
    out = []
    for img, quality in ((full, 85), (thumb, 80)):
        buffer = io.BytesIO()
        img.save(buffer, 'JPEG', quality=quality, optimize=True)
        out.append(ContentFile(buffer.getvalue(), name='photo.jpg'))
    return out


def add_media(feature, kind, upload, *, caption='', client_id=None, user=None):
    """Attach a photo or POV clip. A repeat of the same client_id returns the existing one (safe app retries)."""
    if client_id:
        existing = FeatureMedia.objects.filter(client_id=client_id).first()
        if existing:
            if existing.feature_id != feature.id:
                raise CertificationError('That upload belongs to another feature.')
            return existing, False
    media = FeatureMedia(feature=feature, kind=kind, caption=caption, uploaded_by=user,
                         position=feature.media.count())
    if client_id:
        media.client_id = client_id
    if kind in PHOTO_KINDS:
        try:
            full, thumb = process_photo(upload)
        except Exception as exc:  # Pillow raises several types for files that aren't images
            raise CertificationError("That file isn't a photo we can read.") from exc
        media.file.save('photo.jpg', full, save=False)
        media.thumbnail.save('thumb.jpg', thumb, save=False)
    else:
        media.file.save(upload.name, upload, save=False)
    media.save()
    return media, True


# The workflow.

def submit(feature, user):
    """The person who added a draft (or anyone on the team) marks it ready for a second reviewer."""
    if not is_trail_team(user):
        raise CertificationError('Only the trail team can submit features.')
    if feature.status not in (Certification.DRAFT, Certification.CHANGED):
        raise CertificationError('Only drafts and changed features go for review.')
    if not feature.grade:
        raise CertificationError('Give it a grade before submitting it.')
    feature.submitted_by, feature.submitted_at = user, timezone.now()
    feature.save(update_fields=['submitted_by', 'submitted_at'])
    return feature


def certification_problems(feature, user):
    """Why `user` can't certify `feature` right now, as a list of sentences (empty when they can)."""
    problems = []
    if not can_certify(user):
        problems.append("You don't have permission to certify features.")
    if feature.status not in (Certification.DRAFT, Certification.CHANGED):
        problems.append(f'It is already {feature.get_status_display().lower()}.')
    if not feature.grade:
        problems.append('It needs a grade.')
    if not feature.media.filter(kind__in=PHOTO_KINDS).exists():
        problems.append('It needs at least one photo.')
    if second_reviewer_required() and user.pk in {feature.created_by_id, feature.submitted_by_id}:
        problems.append('A second reviewer has to certify it: not the person who added or submitted it.')
    return problems


def certify(feature, user, now=None):
    problems = certification_problems(feature, user)
    if problems:
        raise CertificationError(' '.join(problems))
    now = now or timezone.now()
    feature.status = Certification.CERTIFIED
    feature.certified_by, feature.certified_at, feature.last_verified_at = user, now, now
    feature.save(update_fields=['status', 'certified_by', 'certified_at', 'last_verified_at'])
    return feature


def flag(feature, user, status):
    """Mark a feature changed (rebuilt, storm damage: needs re-grading) or closed (gone or off limits)."""
    if not is_trail_team(user):
        raise CertificationError('Only the trail team can flag features.')
    if status not in (Certification.CHANGED, Certification.CLOSED):
        raise CertificationError('Flag it as changed or closed.')
    if status == Certification.CHANGED and feature.status != Certification.CERTIFIED:
        raise CertificationError('Only certified features can be flagged as changed.')
    feature.status = status
    # A changed feature has to be reviewed again from scratch.
    feature.submitted_by = feature.submitted_at = None
    feature.save(update_fields=['status', 'submitted_by', 'submitted_at'])
    return feature


def reopen(feature, user):
    """Back to draft, for a closed feature that's rideable again. It then needs certifying like a new one."""
    if not is_trail_team(user):
        raise CertificationError('Only the trail team can reopen features.')
    if feature.status != Certification.CLOSED:
        raise CertificationError('Only closed features can be reopened.')
    feature.status = Certification.DRAFT
    feature.submitted_by = feature.submitted_at = None
    feature.save(update_fields=['status', 'submitted_by', 'submitted_at'])
    return feature


def verify(feature, user, now=None):
    """Someone on the team checked a certified feature and it's as graded."""
    if not is_trail_team(user):
        raise CertificationError('Only the trail team can verify features.')
    if feature.status != Certification.CERTIFIED:
        raise CertificationError('Only certified features can be verified. Re-certify a changed one.')
    feature.last_verified_at = now or timezone.now()
    feature.save(update_fields=['last_verified_at'])
    return feature


def report(feature, user, note='', photo=None):
    """A rider's one-tap "this has changed". Doesn't change the feature: the team reviews it."""
    if not feature.is_live:
        raise CertificationError("That feature isn't open to riders.")
    open_report = FeatureReport.objects.filter(feature=feature, user=user, status=ReportStatus.OPEN).first()
    if open_report:  # one open report per rider per feature; a second tap adds to it
        if note:
            open_report.note = f'{open_report.note}\n{note}'.strip()[:300]
            open_report.save(update_fields=['note'])
        return open_report
    return FeatureReport.objects.create(feature=feature, user=user, note=note[:300], photo=photo or '')


def resolve_report(report_obj, user, status=ReportStatus.RESOLVED):
    if not is_trail_team(user):
        raise CertificationError('Only the trail team can resolve reports.')
    if status not in (ReportStatus.RESOLVED, ReportStatus.DISMISSED):
        raise CertificationError('Resolve or dismiss it.')
    report_obj.status, report_obj.resolved_by, report_obj.resolved_at = status, user, timezone.now()
    report_obj.save(update_fields=['status', 'resolved_by', 'resolved_at'])
    return report_obj


def ladder_warnings(system, features=None):
    """Problems in a trail system's ladders worth fixing: a rung missing between grades, features without a grade.
    [{type, message}]"""
    features = list(features if features is not None else Feature.objects.filter(
        trail__system=system, trail__owner__isnull=True,
    ).exclude(status=Certification.CLOSED))
    warnings = []
    by_type = {}
    for f in features:
        if not f.grade:
            warnings.append({'type': f.type, 'message': f'{f.name} has no grade yet.'})
            continue
        by_type.setdefault(f.type, set()).add(f.grade)
    for type_, grades in sorted(by_type.items()):
        ordered = sorted(grades)
        label = type_.replace('_', ' ').capitalize()
        if ordered[0] > 1:
            warnings.append({'type': type_, 'message': f'{label}: the ladder starts at grade {ordered[0]}. Riders '
                                                       f'new to {label.lower()}s only get grade 1 suggested.'})
        for low, high in zip(ordered, ordered[1:]):
            if high - low > 1:
                missing = ', '.join(str(g) for g in range(low + 1, high))
                warnings.append({'type': type_, 'message': f'{label}: no grade {missing} between {low} and {high}. '
                                                           f'Riders will stall at {low}.'})
    return warnings
