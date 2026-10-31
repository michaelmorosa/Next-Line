import re

from djoser.serializers import UserCreatePasswordRetypeSerializer as BaseCreateSerializer
from rest_framework import serializers

from .models import CustomUser

PHONE_RE = re.compile(r'^\+?[0-9 ()\-]{7,20}$')


class UserCreatePasswordRetypeSerializer(BaseCreateSerializer):
    class Meta(BaseCreateSerializer.Meta):
        model = CustomUser
        fields = ('id', 'username', 'email', 'password')
        extra_kwargs = {'password': {'write_only': True}}

    def validate_email(self, value):
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already in use")
        return value


class UserSerializer(serializers.ModelSerializer):
    """The logged-in rider's own account, including crash-alert settings."""

    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'crash_contact_name', 'crash_contact_phone', 'crash_alerts_enabled')
        read_only_fields = ('id', 'username', 'email')

    def validate_crash_contact_phone(self, value):
        value = value.strip()
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a phone number with country code, like +1 555 555 0123.")
        return value
