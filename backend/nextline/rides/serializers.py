from django.conf import settings
from django.db.models import Count, Q
from rest_framework import serializers

from trails.models import Direction, Feature, Trail
from trails.serializers import FeatureSerializer, progress_for
from trails.views import features_with_counts

from . import level_guide, scoring
from .models import Jump, Ride, TrailEffort


class JumpInputSerializer(serializers.Serializer):
    t = serializers.FloatField(min_value=0)
    airtime_s = serializers.FloatField(min_value=0)


class RideUploadSerializer(serializers.Serializer):
    """A finished recording from the app. Jumps are detected on the phone, since raw accelerometer data is far
    too big to upload; everything else is worked out here from the GPS track."""
    client_id = serializers.UUIDField()
    title = serializers.CharField(max_length=120, required=False, allow_blank=True, default='')
    started_at = serializers.DateTimeField()
    elapsed_s = serializers.FloatField(min_value=0)
    track = serializers.ListField(child=serializers.ListField(allow_empty=False), allow_empty=True)
    jumps = JumpInputSerializer(many=True, required=False, default=list)

    def validate_track(self, value):
        if len(value) > settings.MAX_TRACK_POINTS:
            raise serializers.ValidationError(f"A ride can have at most {settings.MAX_TRACK_POINTS} GPS points.")
        points = []
        for p in value:
            if len(p) < 3 or len(p) > 5:
                raise serializers.ValidationError("Each point is [t, lat, lng, alt, speed].")
            try:
                t, lat, lng = float(p[0]), float(p[1]), float(p[2])
                alt = None if len(p) < 4 or p[3] is None else float(p[3])
                speed = None if len(p) < 5 or p[4] is None else float(p[4])
            except (TypeError, ValueError):
                raise serializers.ValidationError("GPS points must be numbers.")
            points.append([t, lat, lng, alt, speed])
        return points


class EffortSerializer(serializers.ModelSerializer):
    trail_name = serializers.CharField(source='trail.name')
    trail_difficulty = serializers.CharField(source='trail.difficulty')
    trail_direction = serializers.CharField(source='trail.direction')
    previous_best_s = serializers.SerializerMethodField()

    class Meta:
        model = TrailEffort
        fields = ('id', 'trail', 'trail_name', 'trail_difficulty', 'trail_direction', 'start_t', 'elapsed_s',
                  'avg_speed', 'flow_score', 'climb_rate', 'is_pr', 'touchdowns', 'previous_best_s')

    def get_previous_best_s(self, obj):
        return (
            TrailEffort.objects.filter(user=obj.user, trail=obj.trail, started_at__lt=obj.started_at)
            .order_by('elapsed_s').values_list('elapsed_s', flat=True).first()
        )


class JumpSerializer(serializers.ModelSerializer):
    class Meta:
        model = Jump
        fields = ('t', 'airtime_s', 'lat', 'lng')


class RideListSerializer(serializers.ModelSerializer):
    pr_count = serializers.IntegerField(read_only=True)  # descent PRs
    climb_pr_count = serializers.IntegerField(read_only=True)
    lap_count = serializers.IntegerField(read_only=True)
    # The rider's corrected count if they gave one in the check-in, otherwise the estimate.
    touchdowns = serializers.IntegerField(source='touchdown_count', read_only=True)

    class Meta:
        model = Ride
        fields = ('id', 'client_id', 'title', 'started_at', 'elapsed_s', 'moving_s', 'distance_m', 'climb_m',
                  'descent_m', 'jump_count', 'biggest_air_s', 'flow_score', 'climb_rate', 'pr_count', 'climb_pr_count',
                  'lap_count', 'touchdowns', 'touchdowns_detected', 'checked_in_at')

    @staticmethod
    def annotate(queryset):
        return queryset.annotate(
            pr_count=Count(
                'efforts', filter=Q(efforts__is_pr=True, efforts__trail__direction=Direction.DESCENT), distinct=True,
            ),
            climb_pr_count=Count(
                'efforts', filter=Q(efforts__is_pr=True, efforts__trail__direction=Direction.CLIMB), distinct=True,
            ),
            lap_count=Count('efforts', distinct=True),
        )


class RideDetailSerializer(RideListSerializer):
    jumps = JumpSerializer(many=True, read_only=True)
    efforts = EffortSerializer(many=True, read_only=True)
    flow_vs_avg = serializers.SerializerMethodField()
    biggest_air_is_pb = serializers.SerializerMethodField()
    speed_rank = serializers.SerializerMethodField()
    laps = serializers.SerializerMethodField()
    level_gain = serializers.SerializerMethodField()
    features = serializers.SerializerMethodField()

    class Meta(RideListSerializer.Meta):
        fields = RideListSerializer.Meta.fields + (
            'max_speed', 'total_air_s', 'climb_time_s', 'descent_time_s', 'longest_nonstop_climb_m', 'climb_rests',
            'climb_pace_held', 'track', 'confidence', 'crashed', 'notes', 'cleaned_features',
            'jumps', 'efforts', 'laps', 'level_gain', 'flow_vs_avg', 'biggest_air_is_pb', 'speed_rank', 'features',
        )

    def get_level_gain(self, obj):
        return level_guide.ride_level_gain(obj)

    def get_laps(self, obj):
        """Full laps per trail on this ride, most laps first: [{trail, trail_name, laps, clean_laps}]."""
        by_trail = {}
        for effort in obj.efforts.all():
            row = by_trail.setdefault(effort.trail_id, {
                'trail': effort.trail_id, 'trail_name': effort.trail.name, 'direction': effort.trail.direction,
                'laps': 0, 'clean_laps': 0,
            })
            row['laps'] += 1
            row['clean_laps'] += effort.touchdowns == 0
        return sorted(by_trail.values(), key=lambda r: (-r['laps'], r['trail_name']))

    def get_flow_vs_avg(self, obj):
        average = scoring.average_flow_before(obj)
        if obj.flow_score is None or average is None:
            return None
        return round(obj.flow_score - average)

    def get_biggest_air_is_pb(self, obj):
        return obj.biggest_air_s > 0 and obj.biggest_air_s > scoring.biggest_air_before(obj)

    def get_speed_rank(self, obj):
        return scoring.speed_rank(obj)

    def get_features(self, obj):
        """Features on the trails ridden, for the check-in."""
        features = list(
            features_with_counts(obj.user).filter(trail__efforts__ride=obj).distinct().order_by('trail_id', 'id')
        )
        context = {**self.context, 'progress': progress_for(obj.user, features)}
        return FeatureSerializer(features, many=True, context=context).data


class CheckinSerializer(serializers.Serializer):
    """The 10-second post-ride check-in."""
    confidence = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    crashed = serializers.BooleanField(required=False)
    # Null goes back to the estimate.
    touchdowns = serializers.IntegerField(min_value=0, max_value=999, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    cleaned = serializers.ListField(child=serializers.IntegerField(), required=False)
    almost = serializers.ListField(child=serializers.IntegerField(), required=False)

    def validate(self, attrs):
        user = self.context['request'].user
        ids = set(attrs.get('cleaned', [])) | set(attrs.get('almost', []))
        visible = set(Feature.objects.visible_to(user).filter(id__in=ids).values_list('id', flat=True))
        if ids - visible:
            raise serializers.ValidationError("Some of those features don't exist.")
        return attrs


class CrashAlertSerializer(serializers.Serializer):
    lat = serializers.FloatField(required=False, allow_null=True, min_value=-90, max_value=90)
    lng = serializers.FloatField(required=False, allow_null=True, min_value=-180, max_value=180)

