"""The trail team's API (/api/team/...): capture features on site, attach media, review and certify.

Every capture and media upload carries a client_id made by the app, so the app's offline queue can retry until it
hears back without creating anything twice.
"""
from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from progression import content

from . import certification
from .certification import CertificationError
from .models import (
    MAX_GRADE, MIN_GRADE, PHOTO_KINDS, Certification, Feature, FeatureMedia, FeatureReport, FeatureType,
    GradingGuidelines, MediaKind, ReportStatus, Trail, is_trail_team,
)


class IsTrailTeam(permissions.BasePermission):
    message = 'This is for the Next Line trail team.'

    def has_permission(self, request, view):
        return is_trail_team(request.user)


def media_url(request, field):
    return request.build_absolute_uri(field.url) if field else None


def media_data(request, media):
    return {
        'id': media.id, 'kind': media.kind, 'caption': media.caption, 'position': media.position,
        'url': media_url(request, media.file), 'thumbnail': media_url(request, media.thumbnail),
        'client_id': str(media.client_id),
    }


class TeamFeatureSerializer(serializers.ModelSerializer):
    trail_name = serializers.CharField(source='trail.name', read_only=True)
    media = serializers.SerializerMethodField()
    stale = serializers.SerializerMethodField()
    can_certify = serializers.SerializerMethodField()
    certify_problems = serializers.SerializerMethodField()
    open_reports = serializers.SerializerMethodField()

    class Meta:
        model = Feature
        fields = (
            'id', 'client_id', 'trail', 'trail_name', 'name', 'type', 'grade', 'drop_height_m', 'gap_length_m',
            'steepness_deg', 'lat', 'lng', 'position', 'description', 'how_to_ride', 'what_can_go_wrong',
            'has_ride_around', 'ride_around_grade', 'ride_around_note', 'skill_tags', 'status', 'created_by',
            'submitted_by', 'submitted_at', 'certified_by', 'certified_at', 'last_verified_at', 'stale',
            'can_certify', 'certify_problems', 'open_reports', 'media',
        )
        read_only_fields = (
            'position', 'status', 'created_by', 'submitted_by', 'submitted_at', 'certified_by', 'certified_at',
            'last_verified_at',
        )
        extra_kwargs = {'trail': {'required': False}, 'name': {'required': False}}

    def get_media(self, obj):
        return [media_data(self.context['request'], m) for m in obj.media.all()]

    def get_stale(self, obj):
        return certification.is_stale(obj)

    def get_certify_problems(self, obj):
        return certification.certification_problems(obj, self.context['request'].user)

    def get_can_certify(self, obj):
        return not self.get_certify_problems(obj)

    def get_open_reports(self, obj):
        return [
            {'id': r.id, 'note': r.note, 'created_at': r.created_at,
             'photo': media_url(self.context['request'], r.photo)}
            for r in obj.reports.filter(status=ReportStatus.OPEN)
        ]

    def validate_skill_tags(self, tags):
        known = set(content.skills_by_id())
        unknown = [t for t in tags if t not in known]
        if unknown:
            raise ValidationError(f"Unknown skills: {', '.join(unknown)}")
        return list(dict.fromkeys(tags))

    def validate_trail(self, trail):
        if trail.owner_id is not None:
            raise ValidationError('Features go on shared trails.')
        return trail

    def validate(self, attrs):
        ride_around = attrs.get('ride_around_grade')
        if ride_around is not None and not MIN_GRADE <= ride_around <= MAX_GRADE:
            raise ValidationError({'ride_around_grade': f'Grades run {MIN_GRADE}-{MAX_GRADE}.'})
        return attrs


def default_name(feature_type, trail):
    """'Drop 3' for the third drop on a trail, so a quick capture doesn't need typing a name."""
    label = FeatureType(feature_type).label
    return f'{label} {trail.features.filter(type=feature_type).count() + 1}'


@api_view(['GET', 'POST'])
@permission_classes([IsTrailTeam])
def features(request):
    """GET: drafts and everything needing attention. POST: capture a draft (from the app's offline queue)."""
    if request.method == 'GET':
        return Response(review_queue(request))
    client_id = request.data.get('client_id')
    if client_id:
        existing = Feature.objects.filter(client_id=client_id).first()
        if existing:
            return Response(TeamFeatureSerializer(existing, context={'request': request}).data)
    serializer = TeamFeatureSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    trail = data.get('trail') or certification.nearest_trail(data['lat'], data['lng'])
    if trail is None:
        raise ValidationError({'trail': "No trail within reach of this spot. Pick the trail, or move closer to it."})
    if certification.nearest_vertex(trail, data['lat'], data['lng'])[1] > certification.NEAREST_TRAIL_M:
        raise ValidationError({'lat': f"That spot is more than {certification.NEAREST_TRAIL_M} m from {trail.name}."})
    try:
        with transaction.atomic():
            feature = Feature(**{**data, 'trail': trail}, created_by=request.user)
            if not feature.name:
                feature.name = default_name(feature.type, trail)
            certification.place_on_trail(feature)
            feature.save()
    except IntegrityError:  # the same capture arriving twice at once
        feature = Feature.objects.get(client_id=client_id)
        return Response(TeamFeatureSerializer(feature, context={'request': request}).data)
    return Response(TeamFeatureSerializer(feature, context={'request': request}).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsTrailTeam])
def feature_detail(request, pk):
    feature = get_object_or_404(Feature, pk=pk)
    if request.method == 'DELETE':
        if feature.status != Certification.DRAFT:
            raise PermissionDenied('Only drafts can be deleted. Close a live feature instead.')
        feature.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == 'PATCH':
        serializer = TeamFeatureSerializer(feature, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        if feature.status == Certification.CERTIFIED and {'grade', 'type'} & set(serializer.validated_data):
            raise ValidationError('Certified grades are locked. Flag it as changed to regrade it.')
        feature = serializer.save()
    return Response(TeamFeatureSerializer(feature, context={'request': request}).data)


def check_size(upload, kind):
    limit = settings.FEATURE_PHOTO_MAX_MB if kind in PHOTO_KINDS else settings.FEATURE_VIDEO_MAX_MB
    if upload.size > limit * 1024 * 1024:
        raise ValidationError(f'That file is over {limit} MB.')


@api_view(['POST'])
@permission_classes([IsTrailTeam])
@parser_classes([MultiPartParser, FormParser])
def add_media(request, pk):
    feature = get_object_or_404(Feature, pk=pk)
    kind = request.data.get('kind')
    upload = request.FILES.get('file')
    if kind not in MediaKind.values:
        raise ValidationError({'kind': f"Use one of: {', '.join(MediaKind.values)}."})
    if upload is None:
        raise ValidationError({'file': 'Attach the photo or clip.'})
    check_size(upload, kind)
    try:
        media, created = certification.add_media(
            feature, kind, upload, caption=request.data.get('caption', '')[:200],
            client_id=request.data.get('client_id') or None, user=request.user,
        )
    except CertificationError as exc:
        raise ValidationError(str(exc))
    return Response(media_data(request, media), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsTrailTeam])
def delete_media(request, pk, media_id):
    media = get_object_or_404(FeatureMedia, pk=media_id, feature_id=pk)
    media.file.delete(save=False)
    media.thumbnail.delete(save=False)
    media.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


def workflow(action):
    """POST /api/team/features/<id>/<action>/ for submit, certify, flag, reopen and verify."""
    @api_view(['POST'])
    @permission_classes([IsTrailTeam])
    @parser_classes([JSONParser, FormParser])
    def view(request, pk):
        feature = get_object_or_404(Feature, pk=pk)
        try:
            if action == 'flag':
                certification.flag(feature, request.user, request.data.get('status'))
            else:
                getattr(certification, action)(feature, request.user)
        except CertificationError as exc:
            raise ValidationError(str(exc))
        return Response(TeamFeatureSerializer(feature, context={'request': request}).data)
    view.__name__ = f'team_{action}'
    return view


@api_view(['POST'])
@permission_classes([IsTrailTeam])
def resolve_report(request, report_id):
    report_obj = get_object_or_404(FeatureReport, pk=report_id)
    try:
        certification.resolve_report(report_obj, request.user, request.data.get('status', ReportStatus.RESOLVED))
    except CertificationError as exc:
        raise ValidationError(str(exc))
    return Response({'id': report_obj.id, 'status': report_obj.status})


@api_view(['GET'])
@permission_classes([IsTrailTeam])
def guidelines(request):
    doc = GradingGuidelines.get()
    return Response({'body': doc.body, 'updated_at': doc.updated_at})


def review_queue(request):
    """What the team should look at: drafts waiting for a second reviewer, drafts still being filled in, changed
    features, open rider reports and features due a re-check."""
    def rows(qs):
        return TeamFeatureSerializer(qs.select_related('trail').prefetch_related('media', 'reports'), many=True,
                                     context={'request': request}).data

    drafts = Feature.objects.filter(status=Certification.DRAFT, trail__owner__isnull=True)
    reported = Feature.objects.filter(reports__status=ReportStatus.OPEN).distinct()
    return {
        'awaiting_review': rows(drafts.filter(submitted_at__isnull=False).order_by('submitted_at')),
        'drafts': rows(drafts.filter(submitted_at__isnull=True).order_by('-created_at')),
        'changed': rows(Feature.objects.filter(status=Certification.CHANGED).order_by('trail', 'position')),
        'reported': rows(reported.order_by('trail', 'position')),
        'stale': rows(certification.stale_features().filter(status=Certification.CERTIFIED)
                      .order_by('last_verified_at')),
        'counts': {
            'awaiting_review': drafts.filter(submitted_at__isnull=False).count(),
            'open_reports': FeatureReport.objects.filter(status=ReportStatus.OPEN).count(),
        },
    }


@api_view(['GET'])
@permission_classes([IsTrailTeam])
def trails_nearby(request):
    """Shared trails, nearest first, for picking where a capture goes. ?lat=&lng="""
    try:
        lat, lng = float(request.query_params['lat']), float(request.query_params['lng'])
    except (KeyError, ValueError):
        trails = Trail.objects.filter(owner__isnull=True).order_by('name')
        return Response([{'id': t.id, 'name': t.name, 'distance_m': None} for t in trails])
    near = sorted(
        ((t, certification.nearest_vertex(t, lat, lng)[1]) for t in Trail.objects.filter(owner__isnull=True)),
        key=lambda x: x[1],
    )
    return Response([{'id': t.id, 'name': t.name, 'distance_m': round(d)} for t, d in near[:20]])


@api_view(['GET'])
@permission_classes([IsTrailTeam])
def me(request):
    return Response({'is_trail_team': True, 'can_certify': certification.can_certify(request.user)})

