import re

from django.utils import timezone
from djoser.serializers import UserCreatePasswordRetypeSerializer as BaseCreateSerializer
from rest_framework import serializers

from trails import certification
from trails.models import is_trail_team
from trails.skills import safety

from .models import CustomUser

PHONE_RE = re.compile(r'^\+?[0-9 ()\-]{7,20}$')


class UserCreatePasswordRetypeSerializer(BaseCreateSerializer):
    class Meta(BaseCreateSerializer.Meta):
        model = CustomUser
        fields = ('id', 'username', 'email', 'password', 'accepted_safety')
        extra_kwargs = {'password': {'write_only': True}}

    # Riders read and accept the safety notice (trails/content/safety.json) when they sign up.
    accepted_safety = serializers.BooleanField(write_only=True)

    def validate_email(self, value):
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already in use")
        return value

    def validate_accepted_safety(self, value):
        if not value:
            raise serializers.ValidationError('Please read and accept the safety notice.')
        return value

    def validate(self, attrs):
        attrs.pop('accepted_safety', None)
        attrs = super().validate(attrs)
        attrs['safety_version'] = safety()['version']
        attrs['safety_accepted_at'] = timezone.now()
        return attrs


class UserSerializer(serializers.ModelSerializer):
    """The logged-in rider's own account, including crash-alert settings."""

    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'crash_contact_name', 'crash_contact_phone', 'crash_alerts_enabled',
                  'advanced_features', 'safety_version', 'safety_accepted_at', 'safety_current_version',
                  'is_trail_team', 'can_certify')
        read_only_fields = ('id', 'username', 'email', 'safety_accepted_at')

    safety_current_version = serializers.SerializerMethodField()
    is_trail_team = serializers.SerializerMethodField()
    can_certify = serializers.SerializerMethodField()

    def get_safety_current_version(self, obj):
        return safety()['version']

    def get_is_trail_team(self, obj):
        return is_trail_team(obj)

    def get_can_certify(self, obj):
        return certification.can_certify(obj)

    def validate_safety_version(self, value):
        # Riders accept the current notice; sending its version records when.
        if value != safety()['version']:
            raise serializers.ValidationError('Accept the current safety notice.')
        return value

    def update(self, instance, validated_data):
        if 'safety_version' in validated_data:
            instance.safety_accepted_at = timezone.now()
        return super().update(instance, validated_data)

    def validate_crash_contact_phone(self, value):
        value = value.strip()
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a phone number with country code, like +1 555 555 0123.")
        return value
