from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from progression import ride_xp
from trails import rider

from . import achievements, level_guide, scoring
from .alerts import send_crash_alert
from .models import CrashAlert, Ride
from .processing import create_ride
from .serializers import (
    CheckinSerializer, CrashAlertSerializer, RideDetailSerializer, RideListSerializer, RideUploadSerializer,
)


class RideViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                  viewsets.GenericViewSet):

    def get_queryset(self):
        rides = Ride.objects.filter(user=self.request.user)
        if self.action == 'retrieve':
            rides = rides.prefetch_related('jumps', 'efforts__trail')
        return RideListSerializer.annotate(rides)

    def get_serializer_class(self):
        return RideDetailSerializer if self.action == 'retrieve' else RideListSerializer

    def create(self, request):
        upload = RideUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        data = upload.validated_data
        # The app retries uploads until it hears back, so the same recording can arrive twice.
        existing = Ride.objects.filter(user=request.user, client_id=data['client_id']).first()
        if existing:
            return Response(self._detail(existing.pk), status=status.HTTP_200_OK)
        try:
            ride = create_ride(
                request.user, data['client_id'], data['started_at'], data['elapsed_s'], data['track'],
                data['jumps'], data['title'],
            )
        except IntegrityError:
            ride = Ride.objects.get(user=request.user, client_id=data['client_id'])
            return Response(self._detail(ride.pk), status=status.HTTP_200_OK)
        ride_xp.award_ride(ride)
        body = self._detail(ride.pk)
        body['new_achievements'] = achievements.describe(achievements.award(request.user))
        return Response(body, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        # The ledger is append-only, so deleting a ride adds corrections for what it earned.
        with transaction.atomic():
            ride_xp.undo_ride(instance)
            instance.delete()

    def _detail(self, pk):
        ride = RideListSerializer.annotate(Ride.objects.filter(pk=pk)).get()
        return RideDetailSerializer(ride, context={'request': self.request}).data

    @action(detail=True, methods=['post'])
    def checkin(self, request, pk=None):
        ride = self.get_object()
        serializer = CheckinSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            ride = Ride.objects.select_for_update().get(pk=ride.pk)
            for field in ('confidence', 'crashed', 'touchdowns', 'notes'):
                if field in data:
                    setattr(ride, field, data[field])
            ride.checked_in_at = timezone.now()
            ride.save()
        body = self._detail(ride.pk)
        body['new_achievements'] = achievements.describe(achievements.award(request.user))
        return Response(body)


class CrashAlertThrottle(ScopedRateThrottle):
    scope = 'crash'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': request.user.pk}


@api_view(['POST'])
@throttle_classes([CrashAlertThrottle])
def crash_alert(request):
    """Sent by the app when crash detection fired and the rider didn't answer "You OK?"."""
    serializer = CrashAlertSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    alert = send_crash_alert(request.user, serializer.validated_data.get('lat'), serializer.validated_data.get('lng'))
    return Response(
        {'status': alert.status, 'sent': alert.status == CrashAlert.Status.SENT},
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
def progress(request):
    data = scoring.progress(request.user)
    data['suggestions'] = level_guide.suggestions(request.user)
    data['features'] = rider.dashboard(request)
    return Response(data)


@api_view(['GET'])
def level_rules(request):
    return Response(level_guide.level_rules())
