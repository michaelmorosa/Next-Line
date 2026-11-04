import shutil
import tempfile
import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from progression import services

User = get_user_model()

TODAY = date(2026, 11, 4)  # a Wednesday
FOUNDATIONS = ('attack_position', 'braking_control', 'looking_ahead')


def make_user(name='rider'):
    return User.objects.create_user(username=name, email=f'{name}@example.com', password='pw-12345678')


def video(name='clip.mp4'):
    return SimpleUploadedFile(name, b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64, content_type='video/mp4')


def practise(user, skill_id, day=TODAY, **kwargs):
    return services.log_session(user, skill_id, day, client_id=uuid.uuid4(), today=day, **kwargs)


def attempt(user, skill_id, day=TODAY, **kwargs):
    return services.add_attempt(user, skill_id, video(), day, client_id=uuid.uuid4(), today=day, **kwargs)


def make_eligible(user, skill_id, day=TODAY):
    """The minimum the default rules need: 3 sessions over 2 days, plus 1 attempt video."""
    practise(user, skill_id, day - timedelta(days=1))
    practise(user, skill_id, day)
    practise(user, skill_id, day)
    attempt(user, skill_id, day)


def master(user, skill_id, day=TODAY):
    make_eligible(user, skill_id, day)
    return services.master_skill(user, skill_id, confirmed_test=True)


class TempMediaMixin:
    """Keeps uploaded test videos out of the real media folder."""

    def setUp(self):
        super().setUp()
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=folder)
        override.enable()
        self.addCleanup(override.disable)
