import io
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from progression.models import XPEntry
from progression.xp import total_xp
from rides.processing import create_ride
from rides.tests import make_track, upload

from .helpers import make_user

RIDES = [  # (days ago, descent speed, airtime)
    (10, 6, 0.4),
    (5, 5, 0.7),
    (1, 7.5, 0.5),
]


class BackfillTests(TestCase):
    def test_backfill_matches_live_awards(self):
        live = make_user('live')
        client = APIClient()
        client.force_authenticate(live)
        old = make_user('old')  # rode before XP existed
        for days, speed, air in RIDES:
            started = timezone.now() - timedelta(days=days)
            upload(client, make_track(descent_speed=speed), started_at=started, jumps=[{'t': 700, 'airtime_s': air}])
            create_ride(old, f'00000000-0000-0000-0000-00000000000{days % 10}', started, 900,
                        make_track(descent_speed=speed), [{'t': 700, 'airtime_s': air}])
        self.assertEqual(total_xp(old), 0)

        call_command('backfill_xp', stdout=io.StringIO())

        def summary(user):
            return sorted((e.reason, e.amount) for e in XPEntry.objects.filter(user=user))

        self.assertGreater(total_xp(old), 0)
        self.assertEqual(summary(old), summary(live))

    def test_backfill_is_safe_to_rerun(self):
        user = make_user()
        create_ride(user, '00000000-0000-0000-0000-000000000001', timezone.now() - timedelta(days=1), 900,
                    make_track(), [])
        call_command('backfill_xp', stdout=io.StringIO())
        first = total_xp(user)
        call_command('backfill_xp', stdout=io.StringIO())
        self.assertEqual(total_xp(user), first)
