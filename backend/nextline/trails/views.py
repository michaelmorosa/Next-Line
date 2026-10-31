from django.db.models import Count, Max, Min, Q

from rides import achievements
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Feature, FeatureStatus, Trail
from .serializers import (
    FeatureProgressSerializer, FeatureSerializer, TrailDetailSerializer, TrailListSerializer,
    TrailUpdateSerializer, progress_for,
)

# Auto trails show up once ridden this many full laps, so one-off descents don't clutter the list.
AUTO_TRAIL_MIN_LAPS = 2


def features_with_counts(user):
    """Features the rider can see, annotated with how many other riders have cleaned each one."""
    return Feature.objects.visible_to(user).annotate(
        riders_cleaned=Count('progress', filter=Q(progress__status=FeatureStatus.CLEANED) & ~Q(progress__user=user)),
    )


class TrailViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                   viewsets.GenericViewSet):
    """The rider's trails: ones they've ridden, with their times and feature mastery."""

    def get_queryset(self):
        user = self.request.user
        visible_feature = Q(features__approved=True) | Q(features__created_by=user)
        return Trail.objects.visible_to(user).annotate(
            # Full start-to-finish runs, and how many of those had no foot down.
            laps=Count('efforts', filter=Q(efforts__user=user), distinct=True),
            clean_laps=Count('efforts', filter=Q(efforts__user=user, efforts__touchdowns=0), distinct=True),
            ride_count=Count('efforts__ride', filter=Q(efforts__user=user), distinct=True),
            best_s=Min('efforts__elapsed_s', filter=Q(efforts__user=user)),
            last_ridden=Max('efforts__started_at', filter=Q(efforts__user=user)),
            feature_count=Count('features', filter=visible_feature, distinct=True),
            cleaned_count=Count(
                'features__progress',
                filter=visible_feature & Q(features__progress__user=user,
                                           features__progress__status=FeatureStatus.CLEANED),
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
        trail.features_with_counts = features_with_counts(request.user).filter(trail=trail)
        return Response(TrailDetailSerializer(trail, context={'request': request}).data)

    def perform_update(self, serializer):
        # Shared trails are edited in the admin; riders can name and rate the descents they discovered.
        if serializer.instance.owner_id != self.request.user.id:
            raise PermissionDenied("Only your own auto-detected trails can be renamed.")
        serializer.save()

    @action(detail=True, methods=['post'])
    def features(self, request, pk=None):
        trail = get_object_or_404(Trail.objects.visible_to(request.user), pk=pk)
        serializer = FeatureSerializer(data=request.data, context={'request': request, 'trail': trail})
        serializer.is_valid(raise_exception=True)
        # Riders' pins on shared trails wait for approval; on their own trail, or by staff, they're live at once.
        approved = trail.owner_id is not None or request.user.is_staff
        feature = serializer.save(trail=trail, created_by=request.user, approved=approved)
        return Response(FeatureSerializer(feature, context={'request': request}).data, status=status.HTTP_201_CREATED)


class FeatureViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    def get_queryset(self):
        return Feature.objects.visible_to(self.request.user)

    def perform_destroy(self, instance):
        if instance.created_by_id != self.request.user.id:
            raise PermissionDenied("You can only remove features you pinned.")
        instance.delete()

    @action(detail=True, methods=['put'])
    def progress(self, request, pk=None):
        feature = self.get_object()
        serializer = FeatureProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(request.user, feature)
        feature = features_with_counts(request.user).get(pk=feature.pk)
        context = {'request': request, 'progress': progress_for(request.user, [feature])}
        body = FeatureSerializer(feature, context=context).data
        body['new_achievements'] = achievements.describe(achievements.award(request.user))
        return Response(body)
