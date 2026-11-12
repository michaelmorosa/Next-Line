import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from progression import services
from progression.models import XPEntry
from trails.models import Feature, FeatureType, Trail

from .helpers import FOUNDATIONS, TempMediaMixin, make_user, video


class ApiTestCase(TempMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.today = timezone.localdate()

    def session(self, skill_id, day=None, **extra):
        return self.client.post(f'/api/skills/{skill_id}/sessions/', {
            'client_id': str(uuid.uuid4()), 'practiced_on': (day or self.today).isoformat(), **extra,
        }, format='json')

    def attempt(self, skill_id, day=None, upload=None):
        return self.client.post(f'/api/skills/{skill_id}/attempts/', {
            'client_id': str(uuid.uuid4()), 'practiced_on': (day or self.today).isoformat(),
            'video': upload or video(), 'duration_s': 12,
        }, format='multipart')

    def master(self, skill_id):
        self.session(skill_id, self.today - timedelta(days=1))
        self.session(skill_id)
        self.session(skill_id)
        self.attempt(skill_id)
        return self.client.post(f'/api/skills/{skill_id}/master/', {'confirmed_test': True}, format='json')


class SkillTreeApiTests(ApiTestCase):
    def test_new_rider_tree(self):
        res = self.client.get('/api/skills/')
        self.assertEqual(res.status_code, 200)
        states = {s['id']: s['state'] for s in res.data['skills']}
        self.assertEqual({k for k, v in states.items() if v == 'ready'}, set(FOUNDATIONS))
        self.assertEqual(list(states.values()).count('locked'), 47)
        self.assertEqual(set(res.data['next_up']), set(FOUNDATIONS))
        self.assertEqual(res.data['level']['level'], 1)
        self.assertEqual(res.data['level']['title'], 'PQ Punk')
        small = next(s for s in res.data['skills'] if s['id'] == 'small_drops')
        self.assertEqual(sorted(small['prerequisites']), ['manual', 'roll_offs'])
        self.assertGreater(small['depth'], 0)

    def test_requires_login(self):
        self.assertEqual(APIClient().get('/api/skills/').status_code, 401)

    def test_detail_and_unknown(self):
        res = self.client.get('/api/skills/manual/')
        self.assertEqual(res.data['name'], 'Manual')
        self.assertEqual(len(res.data['drills']), 3)
        self.assertIn('small_drops', [u['id'] for u in res.data['unlocks']])
        self.assertEqual(self.client.get('/api/skills/nope/').status_code, 404)

    def test_nearby_tagged_features(self):
        trail = Trail.objects.create(name='Lower Ridge', start_lat=34, start_lng=-118, end_lat=34.01,
                                     end_lng=-118, length_m=1100)
        live = {'status': 'certified', 'grade': 3}
        Feature.objects.create(trail=trail, name='Ledge', type=FeatureType.DROP, lat=34.002, lng=-118, **live)
        Feature.objects.create(trail=trail, name='Far ledge', type=FeatureType.DROP, lat=36, lng=-118, **live)
        Feature.objects.create(trail=trail, name='Berm', type=FeatureType.CORNER, lat=34.003, lng=-118, **live)
        Feature.objects.create(trail=trail, name='Draft ledge', type=FeatureType.DROP, lat=34.001, lng=-118)
        res = self.client.get('/api/skills/roll_offs/?lat=34&lng=-118')
        self.assertEqual([f['name'] for f in res.data['nearby_features']], ['Ledge'])
        self.assertEqual(res.data['nearby_features'][0]['trail_name'], 'Lower Ridge')
        # No location and no rides: an empty list, not an error.
        self.assertEqual(self.client.get('/api/skills/roll_offs/').data['nearby_features'], [])


class PracticeApiTests(ApiTestCase):
    def test_log_session_earns_xp_and_starts_skill(self):
        res = self.session('attack_position', drill_index=0)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['xp_gained'], 10)
        self.assertEqual(res.data['skill']['state'], 'in_progress')
        self.assertEqual(res.data['level']['total'], 10)
        self.assertEqual(res.data['session']['drill'], 'Parking-lot hover')

    def test_detail_has_counts_and_rows(self):
        self.session('attack_position', drill_index=1)
        self.session('attack_position')
        self.attempt('attack_position')
        res = self.client.get('/api/skills/attack_position/')
        self.assertEqual((res.data['sessions'], res.data['attempts']), (2, 1))
        self.assertEqual([h['drill'] for h in res.data['history']], [None, 'Bump soak'])
        self.assertEqual(len(res.data['attempt_videos']), 1)
        self.assertEqual(res.data['requirements']['min_sessions'], 3)

    def test_cap_reported(self):
        for _ in range(3):
            self.session('attack_position')
        res = self.session('attack_position')
        self.assertEqual((res.data['xp_gained'], res.data['capped']), (0, True))
        self.assertEqual(res.data['level']['total'], 30)

    def test_retry_returns_200_without_xp(self):
        body = {'client_id': str(uuid.uuid4()), 'practiced_on': self.today.isoformat()}
        first = self.client.post('/api/skills/attack_position/sessions/', body, format='json')
        again = self.client.post('/api/skills/attack_position/sessions/', body, format='json')
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(again.data['xp_gained'], 0)

    def test_locked_skill_message(self):
        res = self.session('manual')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Manual is locked', res.data['detail'])

    def test_upload_attempt(self):
        res = self.attempt('attack_position')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['xp_gained'], 15)
        self.assertEqual(res.data['skill']['attempts'], 1)
        url = res.data['attempt']['video_url']
        video_res = self.client.get(url)
        self.assertEqual(video_res.status_code, 200)
        self.assertTrue(b''.join(video_res.streaming_content).startswith(b'\x00\x00\x00\x18ftyp'))

    def test_attempt_video_is_private(self):
        url = self.attempt('attack_position').data['attempt']['video_url']
        other = APIClient()
        other.force_authenticate(make_user('other'))
        self.assertEqual(other.get(url).status_code, 404)

    @override_settings(USE_X_ACCEL_REDIRECT=True)
    def test_attempt_video_through_nginx(self):
        url = self.attempt('attack_position').data['attempt']['video_url']
        res = self.client.get(url)
        self.assertTrue(res['X-Accel-Redirect'].startswith('/protected-media/attempts/'))

    def test_rejects_non_video(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        res = self.attempt('attack_position', upload=SimpleUploadedFile('x.txt', b'hi', content_type='text/plain'))
        self.assertEqual(res.status_code, 400)
        self.assertFalse(XPEntry.objects.exists())


class MasteryApiTests(ApiTestCase):
    def test_not_eligible(self):
        self.session('attack_position')
        res = self.client.post('/api/skills/attack_position/master/', {'confirmed_test': True}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('more session', res.data['detail'])

    def test_mastery_unlocks_and_levels_up(self):
        res = self.master('attack_position')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['xp_gained'], 100)
        self.assertEqual(res.data['skill']['state'], 'mastered')
        self.assertEqual({u['id'] for u in res.data['unlocked']}, {'climbing_position', 'wheel_lift', 'pumping'})
        self.assertEqual((res.data['level_before']['level'], res.data['level']['level']), (1, 2))
        self.assertTrue(res.data['leveled_up'])

    def test_multi_prerequisite_unlock_through_api(self):
        for skill in ('attack_position', 'braking_control', 'roll_offs', 'pumping', 'wheel_lift'):
            res = self.master(skill)
            self.assertNotIn('small_drops', [u['id'] for u in res.data['unlocked']])
        res = self.master('manual')
        self.assertIn('small_drops', [u['id'] for u in res.data['unlocked']])
        tree = self.client.get('/api/skills/').data
        self.assertEqual(next(s for s in tree['skills'] if s['id'] == 'small_drops')['state'], 'ready')
        self.assertEqual(tree['mastered_count'], 6)


class LedgerApiTests(ApiTestCase):
    def test_history_newest_first_with_labels(self):
        self.session('attack_position')
        self.attempt('attack_position')
        res = self.client.get('/api/xp/')
        self.assertEqual([e['amount'] for e in res.data['results']], [15, 10])
        self.assertEqual(res.data['results'][0]['label'], 'Attempt video')
        self.assertEqual(res.data['results'][0]['skill_name'], 'Attack position')
        self.assertIsNone(res.data['next_before'])


class ChallengeApiTests(ApiTestCase):
    def test_join_and_progress(self):
        challenge = services.seed_challenges(self.today)[0]
        for skill in ('attack_position', 'pumping', 'wheel_lift'):
            self.master(skill)
        listing = self.client.get('/api/challenges/').data
        self.assertEqual(listing[0]['title'], '30-day manual challenge')
        self.assertFalse(listing[0]['joined'])
        res = self.client.post(f'/api/challenges/{challenge.id}/join/')
        self.assertEqual(res.status_code, 201)
        for _ in range(3):
            self.session('manual')
        self.assertEqual(self.client.get('/api/challenges/').data[0]['progress'], 3)
