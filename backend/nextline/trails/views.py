from django.db.models import Count, Max, Min, Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from . import certification
from .models import Feature, Outcome, Trail
from .serializers import TrailDetailSerializer, TrailListSerializer, TrailUpdateSerializer

# Auto trails show up once ridden this many full laps, so one-off descents don't clutter the list.
AUTO_TRAIL_MIN_LAPS = 2


def features_with_counts(user):
    """Features the rider can see, annotated with how many other riders have cleaned each one."""
    return Feature.objects.visible_to(user).annotate(
        riders_cleaned=Count(
            'logs__user', filter=Q(logs__outcome=Outcome.CLEANED) & ~Q(logs__user=user), distinct=True,
        ),
    )


class TrailViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                   viewsets.GenericViewSet):
    """The rider's trails: ones they've ridden, with their times and features."""

    def get_queryset(self):
        user = self.request.user
        visible = Feature.objects.visible_to(user)
        visible_feature = Q(features__in=visible)
        return Trail.objects.visible_to(user).annotate(
            # Full start-to-finish runs, and how many of those had no foot down.
            laps=Count('efforts', filter=Q(efforts__user=user), distinct=True),
            clean_laps=Count('efforts', filter=Q(efforts__user=user, efforts__touchdowns=0), distinct=True),
            ride_count=Count('efforts__ride', filter=Q(efforts__user=user), distinct=True),
            best_s=Min('efforts__elapsed_s', filter=Q(efforts__user=user)),
            last_ridden=Max('efforts__started_at', filter=Q(efforts__user=user)),
            feature_count=Count('features', filter=visible_feature, distinct=True),
            cleaned_count=Count(
                'features',
                filter=visible_feature & Q(features__logs__user=user, features__logs__outcome=Outcome.CLEANED),
                distinct=True,
            ),
        )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TrailDetailSerializer
        if self.action in ('update', 'partial_update'):
            return TrailUpdateSerializer
        return TrailListSerializer

    def list(self, request):
        trails = self.get_queryset().filter(
            Q(owner__isnull=True, laps__gte=1) | Q(owner=request.user, laps__gte=AUTO_TRAIL_MIN_LAPS)
        ).order_by('-last_ridden')
        return Response(TrailListSerializer(trails, many=True, context={'request': request}).data)

    def retrieve(self, request, pk=None):
        trail = get_object_or_404(self.get_queryset(), pk=pk)
        trail.features_with_counts = features_with_counts(request.user).filter(trail=trail).order_by('position', 'id')
        return Response(TrailDetailSerializer(trail, context={'request': request}).data)

    def perform_update(self, serializer):
        # Shared trails are edited in the admin; riders can name and rate the descents they discovered.
        if serializer.instance.owner_id != self.request.user.id:
            raise PermissionDenied("Only your own auto-detected trails can be renamed.")
        serializer.save()


class FeatureViewSet(viewsets.GenericViewSet):
    """Actions on a feature. The feature page and logging are in rider.py; the team's tools in team.py."""

    def get_queryset(self):
        return Feature.objects.live()

    @action(detail=True, methods=['post'], parser_classes=[JSONParser, MultiPartParser, FormParser])
    def report(self, request, pk=None):
        """A rider's one tap: "this feature has changed". Optional note and photo. Goes to the team's queue."""
        feature = self.get_object()
        photo = request.FILES.get('photo')
        if photo and photo.size > 25 * 1024 * 1024:
            raise ValidationError('That photo is over 25 MB.')
        try:
            report = certification.report(feature, request.user, (request.data.get('note') or '').strip(), photo)
        except certification.CertificationError as exc:
            raise ValidationError(str(exc))
        return Response({'id': report.id, 'status': report.status}, status=status.HTTP_201_CREATED)
