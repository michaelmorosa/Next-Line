from django.db.models import Count, Max, Min, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from progression import ride_xp
from rides import achievements

from .models import Feature, FeatureLog, Outcome, Trail, is_trail_team
from .serializers import (
    FeatureProgressSerializer, FeatureSerializer, TrailDetailSerializer, TrailListSerializer,
    TrailUpdateSerializer, progress_for,
)

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

    @action(detail=True, methods=['post'])
    def features(self, request, pk=None):
        """The trail team adds a draft feature. Riders report changes instead of adding features."""
        if not is_trail_team(request.user):
            raise PermissionDenied('Features are added by the Next Line trail team.')
        trail = get_object_or_404(Trail.objects.filter(owner__isnull=True), pk=pk)
        serializer = FeatureSerializer(data=request.data, context={'request': request, 'trail': trail})
        serializer.is_valid(raise_exception=True)
        position = (trail.features.aggregate(m=Max('position'))['m'] or 0) + 1
        feature = serializer.save(trail=trail, created_by=request.user, position=position)
        return Response(FeatureSerializer(feature, context={'request': request}).data, status=status.HTTP_201_CREATED)


class FeatureViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    def get_queryset(self):
        return Feature.objects.visible_to(self.request.user)

    def perform_destroy(self, instance):
        if not is_trail_team(self.request.user) or instance.is_live:
            raise PermissionDenied('Only the trail team can remove draft features.')
        instance.delete()

    @action(detail=True, methods=['put'])
    def progress(self, request, pk=None):
        """Legacy: the older app's status picker. Cleaned and almost are recorded as logs; locked removes today's."""
        feature = self.get_object()
        serializer = FeatureProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wanted = serializer.validated_data['status']
        today = timezone.localdate()
        if wanted == 'locked':
            FeatureLog.objects.filter(user=request.user, feature=feature, ridden_on=today).delete()
        else:
            FeatureLog.objects.create(
                user=request.user, feature=feature, ridden_on=today, grade_at_log=feature.grade,
                outcome=Outcome.CLEANED if wanted == 'cleaned' else Outcome.SKETCHY,
                note=serializer.validated_data.get('note', ''),
            )
        ride_xp.award_features(request.user)
        feature = features_with_counts(request.user).get(pk=feature.pk)
        context = {'request': request, 'progress': progress_for(request.user, [feature])}
        body = FeatureSerializer(feature, context=context).data
        body['new_achievements'] = achievements.describe(achievements.award(request.user))
        return Response(body)
