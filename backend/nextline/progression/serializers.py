from rest_framework import serializers

from . import content
from .models import Attempt, PracticeSession, XPEntry

VIDEO_TYPES = ('video/mp4', 'video/quicktime')


class SessionInputSerializer(serializers.Serializer):
    client_id = serializers.UUIDField()
    practiced_on = serializers.DateField()  # the rider's local date
    drill_index = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    note = serializers.CharField(required=False, allow_blank=True, max_length=200, default='')


class AttemptInputSerializer(serializers.Serializer):
    client_id = serializers.UUIDField()
    practiced_on = serializers.DateField()
    video = serializers.FileField()
    duration_s = serializers.FloatField(required=False, allow_null=True, min_value=0)
    note = serializers.CharField(required=False, allow_blank=True, max_length=200, default='')

    def validate_video(self, video):
        limits = content.rules()['attempts']
        if video.size > limits['max_mb'] * 1024 * 1024:
            raise serializers.ValidationError(f"Attempt videos can be up to {limits['max_mb']} MB.")
        if getattr(video, 'content_type', None) not in VIDEO_TYPES:
            raise serializers.ValidationError('Upload an MP4 or MOV video.')
        return video


class MasterInputSerializer(serializers.Serializer):
    confirmed_test = serializers.BooleanField()


class SessionSerializer(serializers.ModelSerializer):
    drill = serializers.SerializerMethodField()

    class Meta:
        model = PracticeSession
        fields = ('id', 'skill_id', 'drill_index', 'drill', 'practiced_on', 'logged_at', 'note')

    def get_drill(self, obj):
        drills = content.skills_by_id().get(obj.skill_id, {}).get('drills', [])
        return drills[obj.drill_index]['name'] if obj.drill_index is not None and obj.drill_index < len(drills) else None


class AttemptSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = Attempt
        fields = ('id', 'skill_id', 'video_url', 'duration_s', 'practiced_on', 'created_at', 'note')

    def get_video_url(self, obj):
        # Private: the app fetches this with the rider's token.
        return f'/api/attempts/{obj.id}/video/'


class XPEntrySerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    skill_name = serializers.SerializerMethodField()
    challenge_title = serializers.CharField(source='challenge.title', default=None)

    class Meta:
        model = XPEntry
        fields = ('id', 'amount', 'reason', 'label', 'skill_id', 'skill_name', 'challenge_title', 'created_at')

    def get_label(self, obj):
        return obj.get_reason_display()

    def get_skill_name(self, obj):
        return content.skills_by_id().get(obj.skill_id, {}).get('name') if obj.skill_id else None
