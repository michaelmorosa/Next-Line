import io
import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from progression import xp
from progression.models import Reason, XPEntry

from . import ladders
from .models import Feature, FeatureLog, FeatureMedia, Trail, TrailSystem

User = get_user_model()


class DemoTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)

    def seed(self, *args):
        out = io.StringIO()
        call_command('seed_features_demo', *args, stdout=out)
        return out.getvalue()

    def files(self):
        return [f for _, _, names in os.walk(self.media) for f in names]

    def test_seed(self):
        out = self.seed('--password', 'demo-pass-123')
        system = TrailSystem.objects.get(is_demo=True)
        self.assertEqual(system.trails.count(), 3)
        features = Feature.objects.filter(trail__system=system)
        self.assertEqual(features.count(), 31)
        self.assertEqual(features.filter(status='changed').count(), 1)
        self.assertEqual(len({f.type for f in features}), 8)
        self.assertTrue(all(f.media.exists() for f in features))
        self.assertEqual(len(self.files()), FeatureMedia.objects.count())

        rider = User.objects.get(username='demo')
        self.assertTrue(rider.check_password('demo-pass-123'))
        self.assertEqual(rider.safety_version, 1)
        self.assertGreater(FeatureLog.objects.filter(user=rider).count(), 40)
        self.assertGreaterEqual(xp.level(rider)['level'], 4)
        # Fern Gully is done (its changed feature doesn't count), so the trail bonus was paid.
        self.assertTrue(XPEntry.objects.filter(user=rider, reason=Reason.TRAIL_COMPLETE).exists())
        suggestions = ladders.next_up(rider)
        self.assertEqual(len(suggestions), 3)
        self.assertNotIn('The Huck', [s['feature'].name for s in suggestions])  # grade 8: advanced only
        self.assertIn('Demo rider: demo / demo-pass-123', out)

    def test_rerun_recreates(self):
        self.seed()
        first = xp.total_xp(User.objects.get(username='demo'))
        self.seed()
        self.assertEqual(TrailSystem.objects.count(), 1)
        self.assertEqual(Feature.objects.count(), 31)
        self.assertEqual(xp.total_xp(User.objects.get(username='demo')), first)
        self.assertEqual(len(self.files()), FeatureMedia.objects.count())

    def test_remove_leaves_nothing_behind(self):
        real = TrailSystem.objects.create(name='Real Park', slug='real')
        real_trail = Trail.objects.create(name='Real trail', system=real, start_lat=0, start_lng=0, end_lat=0,
                                          end_lng=0, length_m=1)
        real_feature = Feature.objects.create(trail=real_trail, name='Real drop', lat=0, lng=0, grade=2,
                                              status='certified')
        rider = User.objects.create_user(username='real', email='real@example.com', password='x')
        self.seed()
        out = self.seed('--remove')
        self.assertIn('Removed the demo: 31 features', out)
        self.assertEqual(list(TrailSystem.objects.values_list('slug', flat=True)), ['real'])
        self.assertEqual(list(Feature.objects.all()), [real_feature])
        self.assertFalse(User.objects.filter(username__startswith='demo').exists())
        self.assertTrue(User.objects.filter(pk=rider.pk).exists())
        self.assertEqual(FeatureMedia.objects.count(), 0)
        self.assertEqual(self.files(), [])
        self.assertFalse(XPEntry.objects.exclude(user=rider).exists())
