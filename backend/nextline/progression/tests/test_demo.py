import io

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from progression import xp
from progression.models import ChallengeEntry, XPEntry
from progression.services import challenge_progress
from progression.state import rider_skills

from .helpers import LegacyPointsMixin, TempMediaMixin, User


class DemoRiderTests(LegacyPointsMixin, TempMediaMixin, TestCase):
    def test_demo_rider_history(self):
        out = io.StringIO()
        call_command('seed_progression_demo', password='demo-pass-123', stdout=out)
        user = User.objects.get(username='demo')
        self.assertTrue(user.check_password('demo-pass-123'))
        states = rider_skills(user)
        mastered = {s for s, v in states.items() if v['state'] == 'mastered'}
        self.assertEqual(mastered, {'attack_position', 'braking_control', 'looking_ahead', 'pumping', 'wheel_lift',
                                    'roll_offs'})
        self.assertTrue(states['manual']['eligible'])  # ready to show the mastery flow
        self.assertEqual(states['flat_corners']['state'], 'in_progress')
        self.assertEqual(states['small_drops']['state'], 'locked')
        self.assertEqual(xp.practice_streak(user, timezone.localdate()), 5)
        self.assertEqual(challenge_progress(ChallengeEntry.objects.get(user=user)), 6)
        self.assertTrue(XPEntry.objects.filter(user=user, reason='ride').exists())
        self.assertGreaterEqual(xp.level(user)['level'], 5)
        self.assertIn('Demo rider ready: demo / demo-pass-123', out.getvalue())

    def test_rerun_recreates(self):
        call_command('seed_progression_demo', stdout=io.StringIO())
        first = xp.total_xp(User.objects.get(username='demo'))
        call_command('seed_progression_demo', stdout=io.StringIO())
        self.assertEqual(User.objects.filter(username='demo').count(), 1)
        self.assertEqual(xp.total_xp(User.objects.get(username='demo')), first)
