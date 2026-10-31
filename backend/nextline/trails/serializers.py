from django.utils import timezone
from rest_framework import serializers

from rides.analysis import haversine

from .models import Feature, FeatureProgress, FeatureStatus, Trail

# A pinned feature has to be this close to the trail's line.
MAX_FEATURE_DISTANCE_M = 100


def progress_for(user, features):
    """{feature_id: FeatureProgress} for this rider."""
    return {p.feature_id: p for p in FeatureProgress.objects.filter(user=user, feature__in=features)}


class FeatureSerializer(serializers.ModelSerializer):
    """A feature with the requesting rider's progress. Needs context['progress'] from progress_for()."""
    status = serializers.SerializerMethodField()
    clean_count = serializers.SerializerMethodField()
    first_cleaned_at = serializers.SerializerMethodField()
    note = serializers.SerializerMethodField()
    riders_cleaned = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Feature
        fields = ('id', 'trail', 'name', 'kind', 'lat', 'lng', 'status', 'clean_count', 'first_cleaned_at', 'note',
                  'riders_cleaned', 'is_mine', 'approved')
        read_only_fields = ('trail', 'approved')

    def _progress(self, obj):
        return self.context.get('progress', {}).get(obj.id)

    def get_status(self, obj):
        p = self._progress(obj)
        return p.status if p else FeatureStatus.LOCKED

    def get_clean_count(self, obj):
        p = self._progress(obj)
        return p.clean_count if p else 0

    def get_first_cleaned_at(self, obj):
        p = self._progress(obj)
        return p.first_cleaned_at if p else None

    def get_note(self, obj):
        p = self._progress(obj)
        return p.note if p else ''

    def get_riders_cleaned(self, obj):
        # Annotated by trails.views.features_with_counts; a feature just pinned has none.
        return getattr(obj, 'riders_cleaned', 0)

    def get_is_mine(self, obj):
        request = self.context.get('request')
        return bool(request and obj.created_by_id == request.user.id)

    def validate(self, attrs):
        trail = self.context['trail']
        path = trail.path or [[trail.start_lat, trail.start_lng], [trail.end_lat, trail.end_lng]]
        nearest = min(haversine(attrs['lat'], attrs['lng'], lat, lng) for lat, lng in path)
        if nearest > MAX_FEATURE_DISTANCE_M:
            raise serializers.ValidationError("Pin the feature on the trail, not off to the side.")
        return attrs


class FeatureProgressSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=FeatureStatus.choices)
    note = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def save(self, user, feature):
        progress, _ = FeatureProgress.objects.get_or_create(user=user, feature=feature)
        progress.status = self.validated_data['status']
        if 'note' in self.validated_data:
            progress.note = self.validated_data['note']
        if progress.status == FeatureStatus.CLEANED:
            progress.clean_count = max(progress.clean_count, 1)
            progress.first_cleaned_at = progress.first_cleaned_at or timezone.now()
        progress.save()
        return progress


class TrailListSerializer(serializers.ModelSerializer):
    """Trail with the requesting rider's stats; the view annotates the counts."""
    laps = serializers.IntegerField(read_only=True)
    clean_laps = serializers.IntegerField(read_only=True)
    ride_count = serializers.IntegerField(read_only=True)
    best_s = serializers.FloatField(read_only=True)
    last_ridden = serializers.DateTimeField(read_only=True)
    feature_count = serializers.IntegerField(read_only=True)
    cleaned_count = serializers.IntegerField(read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Trail
        fields = ('id', 'name', 'direction', 'difficulty', 'is_auto', 'is_mine', 'length_m', 'drop_m', 'laps',
                  'clean_laps',
                  'ride_count', 'best_s', 'last_ridden', 'feature_count', 'cleaned_count')

    def get_is_mine(self, obj):
        return obj.owner_id == self.context['request'].user.id


class TrailDetailSerializer(TrailListSerializer):
    features = serializers.SerializerMethodField()
    efforts = serializers.SerializerMethodField()

    class Meta(TrailListSerializer.Meta):
        fields = TrailListSerializer.Meta.fields + ('start_lat', 'start_lng', 'end_lat', 'end_lng', 'path',
                                                    'features', 'efforts')

    def get_features(self, obj):
        features = list(obj.features_with_counts)
        context = {**self.context, 'progress': progress_for(self.context['request'].user, features)}
        return FeatureSerializer(features, many=True, context=context).data

    def get_efforts(self, obj):
        efforts = obj.efforts.filter(user=self.context['request'].user).order_by('started_at')
        return [
            {'id': e.id, 'ride': e.ride_id, 'started_at': e.started_at, 'elapsed_s': e.elapsed_s,
             'flow_score': e.flow_score, 'climb_rate': e.climb_rate, 'is_pr': e.is_pr, 'touchdowns': e.touchdowns}
            for e in efforts
        ]


class TrailUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trail
        fields = ('name', 'difficulty')
