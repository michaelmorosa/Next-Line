import io
import shutil
import tempfile
import zipfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from progression import services, xp
from progression.models import Challenge, Reason, XPEntry
from progression.summary import challenge_list

from .models import Feature, FeatureLog, FeatureMedia, Trail, TrailSystem

User = get_user_model()


def jpeg(size=(1600, 1200)):
    buffer = io.BytesIO()
    Image.new('RGB', size, (80, 110, 70)).save(buffer, 'JPEG')
    return buffer.getvalue()


class Base(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.rider = User.objects.create_user(username='rider', email='r@example.com', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.rider)
        self.system = TrailSystem.objects.create(name='Ridge Park', slug='ridge')
        self.trail = Trail.objects.create(name='Upper Ridge', system=self.system, start_lat=0, start_lng=0, end_lat=0,
                                          end_lng=0, length_m=1)

    def feature(self, grade=3, type='drop', **extra):
        return Feature.objects.create(trail=self.trail, name=f'{type} {grade}', type=type, grade=grade, lat=0, lng=0,
                                      status='certified', last_verified_at=timezone.now(), **extra)

    def log(self, feature, outcome='cleaned', days_ago=0):
        res = self.client.post(f'/api/features/{feature.id}/log/', {
            'outcome': outcome, 'ridden_on': str(timezone.localdate() - timedelta(days=days_ago))}, format='json')
        return res.data['logs'][0]['id']


class ShareCardTests(Base):
    def test_first_clean_card_in_both_sizes(self):
        f = self.feature(how_to_ride='Speed, then pop.')
        media = FeatureMedia(feature=f, kind='feature')
        media.file.save('photo.jpg', ContentFile(jpeg()), save=True)
        log_id = self.log(f)
        for size, dims in (('story', (1080, 1920)), ('feed', (1080, 1350))):
            res = self.client.get(f'/api/logs/{log_id}/share-card/?size={size}')
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res['Content-Type'], 'image/jpeg')
            self.assertEqual(Image.open(io.BytesIO(res.content)).size, dims)

    def test_card_without_a_photo(self):
        log_id = self.log(self.feature())
        self.assertEqual(self.client.get(f'/api/logs/{log_id}/share-card/').status_code, 200)

    def test_only_for_your_own_cleans(self):
        f = self.feature()
        walked = self.log(f, 'walked')
        self.assertEqual(self.client.get(f'/api/logs/{walked}/share-card/').status_code, 400)
        cleaned = self.log(f)
        other = APIClient()
        other.force_authenticate(User.objects.create_user(username='o', email='o@example.com', password='x'))
        self.assertEqual(other.get(f'/api/logs/{cleaned}/share-card/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/logs/{cleaned}/share-card/?size=huge').status_code, 400)

    def test_feature_of_the_week_export(self):
        f = self.feature(how_to_ride='Speed, then pop.', has_ride_around=True, ride_around_grade=1)
        FeatureMedia(feature=f, kind='feature').file.save('photo.jpg', ContentFile(jpeg()), save=True)
        FeatureMedia(feature=f, kind='pov').file.save('pov.mp4', ContentFile(b'\x00' * 64), save=True)
        admin = User.objects.create_superuser(username='boss', email='b@example.com', password='x')
        self.client.force_login(admin)
        res = self.client.post('/admin/trails/feature/', {'action': 'feature_of_the_week', '_selected_action': [f.id]})
        self.assertEqual(res['Content-Type'], 'application/zip')
        z = zipfile.ZipFile(io.BytesIO(res.content))
        self.assertEqual(sorted(z.namelist()), ['card-feed.jpg', 'card-story.jpg', 'photo.jpg', 'post.txt'])
        post = z.read('post.txt').decode()
        self.assertIn('Grade 3 drop on Upper Ridge, Ridge Park', post)
        self.assertIn('Speed, then pop.', post)
        self.assertIn('/media/features/', post)  # the POV clip link
        self.assertIn('Ride-around: yes, grade 1', post)


class FeatureChallengeTests(Base):
    def challenge(self, **fields):
        today = timezone.localdate()
        defaults = {'slug': 'c', 'title': 'C', 'goal_type': 'next_features', 'goal_count': 3,
                    'starts_on': today - timedelta(days=5), 'ends_on': today + timedelta(days=20)}
        return Challenge.objects.create(**{**defaults, **fields})

    def test_next_three_features(self):
        before = self.feature(1)
        self.log(before)  # cleaned before joining: not new
        # Windows clocks can give the log and the join the same timestamp.
        FeatureLog.objects.filter(feature=before).update(logged_at=timezone.now() - timedelta(minutes=1))
        challenge = self.challenge()
        entry = services.join_challenge(self.rider, challenge)
        new = [self.feature(g, t) for g, t in ((1, 'jump'), (1, 'corner'), (2, 'drop'))]
        self.log(before)
        self.log(new[0], 'sketchy')  # not a clean
        self.assertEqual(services.challenge_progress(entry), 0)
        self.log(new[0])
        self.log(new[0])  # the same feature twice counts once
        self.log(new[1])
        self.assertEqual(services.challenge_progress(entry), 2)
        self.log(new[2])
        entry.refresh_from_db()
        self.assertIsNotNone(entry.completed_at)
        self.assertEqual(XPEntry.objects.get(user=self.rider, reason=Reason.CHALLENGE).amount, 50)

    def test_every_grade_3_corner(self):
        targets = [self.feature(3, 'corner'), self.feature(3, 'corner')]
        self.feature(4, 'corner')
        self.feature(3, 'drop')
        challenge = self.challenge(slug='corners', goal_type='features', goal_count=0, system=self.system,
                                   feature_type='corner', grade_min=3, grade_max=3)
        listing = {c['slug']: c for c in challenge_list(self.rider)}
        self.assertEqual(listing['corners']['goal_text'], 'Clean every grade 3 corner at Ridge Park (2)')
        self.assertEqual(listing['corners']['goal_count'], 2)
        entry = services.join_challenge(self.rider, challenge)
        self.log(targets[0])
        self.assertEqual(services.challenge_progress(entry), 1)
        self.log(targets[1])
        entry.refresh_from_db()
        self.assertIsNotNone(entry.completed_at)

    def test_upcoming_challenge_listed_but_not_joinable(self):
        today = timezone.localdate()
        upcoming = self.challenge(slug='soon', starts_on=today + timedelta(days=20), ends_on=today + timedelta(days=50))
        self.challenge(slug='far', starts_on=today + timedelta(days=90), ends_on=today + timedelta(days=120))
        listing = {c['slug']: c for c in challenge_list(self.rider)}
        self.assertTrue(listing['soon']['upcoming'])
        self.assertNotIn('far', listing)
        self.assertEqual(listing['soon']['goal_text'], "Clean 3 features you haven't cleaned before")
        self.assertEqual(self.client.post(f'/api/challenges/{upcoming.id}/join/').status_code, 400)

    def test_level_shown_on_card_is_current(self):
        log_id = self.log(self.feature(5))
        self.assertEqual(xp.level(self.rider)['total'], 100)
        self.assertEqual(self.client.get(f'/api/logs/{log_id}/share-card/').status_code, 200)
