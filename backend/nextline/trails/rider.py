"""What riders use: trail systems, feature pages, one-tap logging, ladders and next up."""
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from progression import content, feature_points, xp
from progression.models import XPEntry
from rides import achievements

from . import certification, ladders, share, skills, strengths
from .models import (
    PHOTO_KINDS, Certification, Feature, FeatureLog, FeatureType, MediaKind, Outcome, Trail, TrailSystem,
)


def media_url(request, field):
    return request.build_absolute_uri(field.url) if field else None


def cover_photo(feature):
    """The feature photo if there is one, else any photo. Uses prefetched media when available."""
    photos = [m for m in feature.media.all() if m.kind in PHOTO_KINDS]
    return next((m for m in photos if m.kind == MediaKind.FEATURE), photos[0] if photos else None)


def feature_card(request, f, record):
    """A feature as riders see it in lists."""
    cover = cover_photo(f)
    return {
        'id': f.id, 'name': f.name, 'type': f.type, 'type_label': f.get_type_display(), 'grade': f.grade,
        'trail': f.trail_id, 'trail_name': f.trail.name, 'position': f.position, 'lat': f.lat, 'lng': f.lng,
        'certification': f.status, 'changed': f.status == Certification.CHANGED,
        'stale': certification.is_stale(f), 'has_ride_around': f.has_ride_around,
        'ride_around_grade': f.ride_around_grade,
        'thumbnail': media_url(request, cover.thumbnail or cover.file) if cover else None,
        'my_status': record.status(f.id), 'my_cleans': record.cleans.get(f.id, 0),
    }


def live_features():
    return Feature.objects.live().select_related('trail').prefetch_related('media')


# Trail systems.

def system_summaries(user, systems):
    cleaned = ladders.RiderRecord(user).cleans
    out = []
    for s in systems:
        feature_ids = list(Feature.objects.live().filter(trail__system=s).values_list('id', flat=True))
        out.append({
            'id': s.id, 'slug': s.slug, 'name': s.name, 'location': s.location, 'lat': s.lat, 'lng': s.lng,
            'description': s.description, 'is_demo': s.is_demo,
            'trail_count': s.trails.filter(owner__isnull=True).count(),
            'feature_count': len(feature_ids), 'cleaned_count': sum(1 for i in feature_ids if cleaned.get(i)),
        })
    return out


@api_view(['GET'])
def systems(request):
    return Response(system_summaries(request.user, TrailSystem.objects.all()))


def next_up_data(request, user, system=None):
    record = ladders.RiderRecord(user)
    out = []
    for s in ladders.next_up(user, system):
        row = feature_card(request, s['feature'], record)
        row.update(reason=s['reason'], step_up=s['step_up'])
        out.append(row)
    return out


@api_view(['GET'])
def system_detail(request, pk):
    system = get_object_or_404(TrailSystem, pk=pk)
    record = ladders.RiderRecord(request.user)
    features = list(live_features().filter(trail__system=system).order_by('trail__name', 'position'))
    trails = Trail.objects.filter(system=system, owner__isnull=True).order_by('name')
    by_trail = {}
    for f in features:
        by_trail.setdefault(f.trail_id, []).append(f)
    return Response({
        **system_summaries(request.user, [system])[0],
        'trails': [
            {
                'id': t.id, 'name': t.name, 'difficulty': t.difficulty, 'difficulty_label': t.get_difficulty_display(),
                'direction': t.direction, 'length_m': t.length_m, 'drop_m': t.drop_m, 'path': t.path,
                'feature_count': len(by_trail.get(t.id, [])),
                'cleaned_count': sum(1 for f in by_trail.get(t.id, []) if record.cleans.get(f.id)),
            }
            for t in trails
        ],
        'features': [feature_card(request, f, record) for f in features],
        'ladders': [{k: v for k, v in ladder.items() if k != 'rungs'} for ladder in ladders.ladders(request.user, system)],
        'next_up': next_up_data(request, request.user, system),
    })


@api_view(['GET'])
def trail_features(request, pk):
    """A shared trail's page: its features in riding order with the rider's status on each."""
    trail = get_object_or_404(Trail, pk=pk, owner__isnull=True)
    record = ladders.RiderRecord(request.user)
    features = live_features().filter(trail=trail).order_by('position', 'id')
    return Response({
        'id': trail.id, 'name': trail.name, 'system': trail.system_id,
        'system_name': trail.system.name if trail.system_id else None,
        'difficulty': trail.difficulty, 'difficulty_label': trail.get_difficulty_display(),
        'direction': trail.direction, 'length_m': trail.length_m, 'drop_m': trail.drop_m, 'path': trail.path,
        'features': [feature_card(request, f, record) for f in features],
        'safety': skills.safety()['short'],
    })


# Features.

def history(user, feature):
    logs = list(FeatureLog.objects.filter(user=user, feature=feature))
    points = {}
    for e in XPEntry.objects.filter(user=user, log_id__in=[log.id for log in logs]):
        points[e.log_id] = points.get(e.log_id, 0) + e.amount
    return [{'id': log.id, 'outcome': log.outcome, 'ridden_on': log.ridden_on, 'note': log.note,
             'points': points.get(log.id, 0)} for log in logs]


@api_view(['GET'])
def feature_detail(request, pk):
    feature = get_object_or_404(live_features(), pk=pk)
    record = ladders.RiderRecord(request.user)
    notices = []
    if feature.status == Certification.CHANGED:
        notices.append('This feature has changed since we graded it. Look it over before you ride it.')
    if certification.is_stale(feature):
        notices.append('Not recently verified: our team hasn\'t checked this feature in over a year.')
    safety = skills.safety()
    return Response({
        **feature_card(request, feature, record),
        'description': feature.description, 'how_to_ride': feature.how_to_ride,
        'what_can_go_wrong': feature.what_can_go_wrong, 'ride_around_note': feature.ride_around_note,
        'measurements': {k: getattr(feature, k) for k in ('drop_height_m', 'gap_length_m', 'steepness_deg')
                         if getattr(feature, k) is not None},
        'media': [
            {'id': m.id, 'kind': m.kind, 'kind_label': m.get_kind_display(), 'caption': m.caption,
             'url': media_url(request, m.file), 'thumbnail': media_url(request, m.thumbnail)}
            for m in feature.media.all()
        ],
        'last_verified_at': feature.last_verified_at,
        'notices': notices,
        'history': history(request.user, feature),
        'stuck': skills.tips(feature),
        'safety': {'title': safety['title'], 'short': safety['short'], 'full': safety['full'],
                   'needs_legal_review': safety['needs_legal_review']},
        'first_clean_points': content.rules()['xp']['first_clean_per_grade'] * (feature.grade or 0),
    })


class LogSerializer(serializers.Serializer):
    feature = serializers.IntegerField(required=False)
    outcome = serializers.ChoiceField(choices=Outcome.choices)
    ridden_on = serializers.DateField(required=False)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    client_id = serializers.UUIDField(required=False)
    ride = serializers.IntegerField(required=False, allow_null=True)

    def validate_ridden_on(self, value):
        # The app sends the rider's local date, which can be a day ahead of the server's.
        if value > timezone.localdate() + timedelta(days=1):
            raise ValidationError("That date hasn't happened yet.")
        return value


def create_log(user, feature, data):
    """One log, safe to retry with the same client_id. Returns (log, created)."""
    if not feature.is_live:
        raise ValidationError("That feature isn't open for logging.")
    client_id = data.get('client_id') or uuid.uuid4()
    existing = FeatureLog.objects.filter(user=user, client_id=client_id).first()
    if existing:
        return existing, False
    ride_id = data.get('ride')
    if ride_id and not user.rides.filter(pk=ride_id).exists():
        raise ValidationError('That ride isn\'t yours.')
    try:
        with transaction.atomic():
            log = FeatureLog.objects.create(
                user=user, feature=feature, outcome=data['outcome'], note=data.get('note', ''),
                ridden_on=data.get('ridden_on') or timezone.localdate(), grade_at_log=feature.grade,
                client_id=client_id, ride_id=ride_id,
            )
    except IntegrityError:
        return FeatureLog.objects.get(user=user, client_id=client_id), False
    feature_points.log_created(log)
    return log, True


def log_result(request, logs, level_before):
    """What the app shows after logging: points per log, first cleans (for share cards), level change."""
    entries = XPEntry.objects.filter(user=request.user, log_id__in=[log.id for log in logs])
    by_log = {}
    for e in entries:
        by_log.setdefault(e.log_id, []).append({'label': e.get_reason_display(), 'amount': e.amount})
    level = xp.level(request.user)
    return {
        'logs': [
            {'id': log.id, 'feature': log.feature_id, 'feature_name': log.feature.name, 'outcome': log.outcome,
             'ridden_on': log.ridden_on, 'note': log.note, 'points': by_log.get(log.id, []),
             'first_clean': any(p['label'] == 'First clean' for p in by_log.get(log.id, []))}
            for log in logs
        ],
        'points': sum(e.amount for e in entries),
        'level_before': level_before,
        'level': level,
        'leveled_up': level['level'] > level_before['level'],
        'new_achievements': achievements.describe(achievements.award(request.user)),
    }


@api_view(['POST'])
def log_feature(request, pk):
    """One tap: cleaned it, rode it sketchy, or walked it."""
    feature = get_object_or_404(live_features(), pk=pk)
    serializer = LogSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    before = xp.level(request.user)
    log, created = create_log(request.user, feature, serializer.validated_data)
    return Response(log_result(request, [log], before), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class BatchSerializer(serializers.Serializer):
    ridden_on = serializers.DateField(required=False)
    ride = serializers.IntegerField(required=False, allow_null=True)
    logs = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=100)


@api_view(['POST'])
def log_batch(request):
    """"Log this trail": several features at once after a ride. {ridden_on, ride, logs: [{feature, outcome, ...}]}"""
    batch = BatchSerializer(data=request.data)
    batch.is_valid(raise_exception=True)
    parsed = []
    for row in batch.validated_data['logs']:
        s = LogSerializer(data=row)
        s.is_valid(raise_exception=True)
        if 'feature' not in s.validated_data:
            raise ValidationError({'logs': 'Each log needs a feature.'})
        parsed.append({'ridden_on': batch.validated_data.get('ridden_on'), 'ride': batch.validated_data.get('ride'),
                       **s.validated_data})
    features = {f.id: f for f in live_features().filter(pk__in=[d['feature'] for d in parsed])}
    missing = [d['feature'] for d in parsed if d['feature'] not in features]
    if missing:
        raise ValidationError({'logs': f'Not open for logging: {missing}'})
    before = xp.level(request.user)
    with transaction.atomic():
        logs = [create_log(request.user, features[d['feature']], d)[0] for d in parsed]
    return Response(log_result(request, logs, before), status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
def log_detail(request, pk):
    log = get_object_or_404(FeatureLog, pk=pk)
    if log.user_id != request.user.id:
        raise PermissionDenied('That log isn\'t yours.')
    if request.method == 'DELETE':
        feature_points.delete_log(log)
        return Response(status=status.HTTP_204_NO_CONTENT)
    note = request.data.get('note')
    if note is None or len(note) > 200:
        raise ValidationError({'note': 'Send a note of up to 200 characters.'})
    log.note = note
    log.save(update_fields=['note'])
    return Response({'id': log.id, 'note': log.note})


@api_view(['GET'])
def share_card(request, pk):
    """The share card for a clean, as a JPEG. ?size=story (1080x1920, Stories and TikTok) or feed (1080x1350)."""
    log = get_object_or_404(FeatureLog.objects.select_related('feature__trail'), pk=pk, user=request.user)
    if log.outcome != Outcome.CLEANED:
        raise ValidationError('Share cards are for cleans.')
    size = request.query_params.get('size', 'story')
    if size not in share.SIZES:
        raise ValidationError(f"size is one of: {', '.join(share.SIZES)}")
    first = not FeatureLog.objects.filter(
        user=request.user, feature=log.feature, outcome=Outcome.CLEANED,
    ).exclude(pk=log.pk).filter(ridden_on__lt=log.ridden_on).exists()
    image = share.render(log.feature, size, headline='First clean' if first else 'Cleaned it',
                         rider_line=share.rider_line(xp.level(request.user)))
    response = HttpResponse(image, content_type='image/jpeg')
    response['Content-Disposition'] = f'inline; filename="next-line-{log.feature_id}-{size}.jpg"'
    return response


# Ladders and next up.

@api_view(['GET'])
def system_ladders(request, pk):
    system = get_object_or_404(TrailSystem, pk=pk)
    return Response({'system': system.id, 'system_name': system.name, 'ladders': ladders.ladders(request.user, system)})


@api_view(['GET'])
def next_up(request):
    system = request.query_params.get('system')
    system = get_object_or_404(TrailSystem, pk=system) if system else None
    return Response({
        'next_up': next_up_data(request, request.user, system),
        'advanced_features': request.user.advanced_features,
        'advanced_above_grade': ladders.rules()['advanced_above_grade'],
    })


# The dashboard's feature section.

def cleaned_by_type(user):
    record = ladders.RiderRecord(user)
    counts = (
        Feature.objects.filter(pk__in=[f for f, n in record.cleans.items() if n])
        .values('type').annotate(n=Count('id'))
    )
    by_type = {row['type']: row['n'] for row in counts}
    return [
        {'type': t, 'label': FeatureType(t).label, 'cleaned': by_type[t], 'best_grade': record.best[t] or None}
        for t in FeatureType.values if by_type.get(t)
    ]


def recent_activity(user, limit=10):
    logs = list(FeatureLog.objects.filter(user=user).select_related('feature__trail')[:limit])
    points = {}
    for e in XPEntry.objects.filter(user=user, log_id__in=[log.id for log in logs]):
        points[e.log_id] = points.get(e.log_id, 0) + e.amount
    return [
        {'id': log.id, 'feature': log.feature_id, 'feature_name': log.feature.name, 'type': log.feature.type,
         'grade': log.grade_at_log, 'trail_name': log.feature.trail.name, 'outcome': log.outcome,
         'ridden_on': log.ridden_on, 'points': points.get(log.id, 0)}
        for log in logs
    ]


def dashboard(request):
    user = request.user
    return {
        'next_up': next_up_data(request, user),
        'cleaned_by_type': cleaned_by_type(user),
        'strengths': strengths.summary(user),
        'recent': recent_activity(user),
        'features_cleaned': sum(1 for n in ladders.RiderRecord(user).cleans.values() if n),
    }


@api_view(['GET'])
def safety(request):
    return Response(skills.safety())

