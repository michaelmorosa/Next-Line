import io
import shutil
import tempfile
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from progression import content

from . import certification
from .apps import TRAIL_TEAM_GROUP
from .models import Feature, FeatureMedia, FeatureReport, Trail, TrailSystem

User = get_user_model()
PATH = [[45.0, -122.0 + i * 0.0005] for i in range(21)]  # about 800 m, west to east


def photo(size=(3000, 2000), name='photo.jpg'):
    buffer = io.BytesIO()
    Image.new('RGB', size, (90, 120, 60)).save(buffer, 'JPEG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


def rules_with(**verification):
    rules = content.rules()
    return {**rules, 'verification': {**rules['verification'], **verification}}


class TeamTestCase(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

        self.system = TrailSystem.objects.create(name='Ridge Park', slug='ridge')
        self.trail = Trail.objects.create(name='Upper Ridge', system=self.system, start_lat=45, start_lng=-122,
                                          end_lat=45, end_lng=-121.99, length_m=800, path=PATH)
        self.alice, self.alice_client = self.member('alice')
        self.bob, self.bob_client = self.member('bob')
        self.rider = User.objects.create_user(username='rider', email='rider@example.com', password='x')
        self.rider_client = APIClient()
        self.rider_client.force_authenticate(self.rider)

    def member(self, name):
        user = User.objects.create_user(username=name, email=f'{name}@example.com', password='x')
        user.groups.add(Group.objects.get(name=TRAIL_TEAM_GROUP))
        user = User.objects.get(pk=user.pk)
        client = APIClient()
        client.force_authenticate(user)
        return user, client

    def capture(self, client=None, at=10, **body):
        lat, lng = PATH[at]
        data = {'type': 'drop', 'grade': 3, 'lat': lat, 'lng': lng, 'client_id': str(uuid.uuid4()), **body}
        return (client or self.alice_client).post('/api/team/features/', data, format='json')

    def upload(self, feature_id, kind='feature', client=None, **extra):
        return (client or self.alice_client).post(
            f'/api/team/features/{feature_id}/media/', {'kind': kind, 'file': photo(), **extra}, format='multipart')

    def ready(self, **body):
        """A captured draft with a photo, submitted by Alice."""
        feature_id = self.capture(**body).data['id']
        self.upload(feature_id)
        self.alice_client.post(f'/api/team/features/{feature_id}/submit/')
        return feature_id


class CaptureTests(TeamTestCase):
    def test_capture_on_site(self):
        res = self.capture(drop_height_m=0.9)
        self.assertEqual(res.status_code, 201, res.data)
        f = Feature.objects.get(pk=res.data['id'])
        self.assertEqual((f.trail, f.status, f.name, f.created_by), (self.trail, 'draft', 'Drop 1', self.alice))
        self.assertEqual(f.drop_height_m, 0.9)

    def test_retrying_a_capture_creates_it_once(self):
        client_id = str(uuid.uuid4())
        first = self.capture(client_id=client_id)
        again = self.capture(client_id=client_id)
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.data['id'], again.data['id'])
        self.assertEqual(Feature.objects.count(), 1)

    def test_no_trail_nearby(self):
        res = self.alice_client.post('/api/team/features/', {'type': 'drop', 'grade': 2, 'lat': 46, 'lng': -122},
                                     format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('No trail', str(res.data))

    def test_captures_are_placed_in_riding_order(self):
        top = self.capture(at=2).data['id']
        bottom = self.capture(at=18).data['id']
        middle = self.capture(at=10, type='jump').data['id']
        order = list(Feature.objects.order_by('position').values_list('id', flat=True))
        self.assertEqual(order, [top, middle, bottom])

    def test_point_must_be_near_the_chosen_trail(self):
        res = self.capture(trail=self.trail.id, lat=45.01)
        self.assertEqual(res.status_code, 400)
        self.assertIn('150 m', str(res.data))

    def test_riders_cannot_use_the_team_api(self):
        self.assertEqual(self.capture(client=self.rider_client).status_code, 403)
        self.assertEqual(self.rider_client.get('/api/team/features/').status_code, 403)

    def test_unknown_skill_tags_rejected(self):
        res = self.capture(skill_tags=['small_drops', 'levitation'])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.capture(skill_tags=['small_drops']).status_code, 201)


class MediaTests(TeamTestCase):
    def test_photos_are_resized_with_a_thumbnail(self):
        feature_id = self.capture().data['id']
        res = self.upload(feature_id, caption='From the approach')
        self.assertEqual(res.status_code, 201, res.data)
        media = FeatureMedia.objects.get()
        with Image.open(media.file.path) as full, Image.open(media.thumbnail.path) as thumb:
            self.assertEqual(max(full.size), certification.PHOTO_LONG_EDGE)
            self.assertEqual(max(thumb.size), certification.THUMB_LONG_EDGE)
        self.assertTrue(res.data['url'].startswith('http://testserver/media/features/'))

    def test_retrying_an_upload_stores_it_once(self):
        feature_id = self.capture().data['id']
        client_id = str(uuid.uuid4())
        self.assertEqual(self.upload(feature_id, client_id=client_id).status_code, 201)
        self.assertEqual(self.upload(feature_id, client_id=client_id).status_code, 200)
        self.assertEqual(FeatureMedia.objects.count(), 1)

    def test_not_a_photo(self):
        feature_id = self.capture().data['id']
        bad = SimpleUploadedFile('x.jpg', b'not an image', content_type='image/jpeg')
        res = self.alice_client.post(f'/api/team/features/{feature_id}/media/', {'kind': 'feature', 'file': bad},
                                     format='multipart')
        self.assertEqual(res.status_code, 400)

    def test_pov_clip_is_stored_as_is(self):
        feature_id = self.capture().data['id']
        clip = SimpleUploadedFile('pov.mp4', b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64, content_type='video/mp4')
        res = self.alice_client.post(f'/api/team/features/{feature_id}/media/', {'kind': 'pov', 'file': clip},
                                     format='multipart')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data['url'].endswith('.mp4'))
        self.assertIsNone(res.data['thumbnail'])


class CertifyTests(TeamTestCase):
    def test_submit_needs_a_grade(self):
        feature_id = self.capture(grade=None).data['id']
        res = self.alice_client.post(f'/api/team/features/{feature_id}/submit/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('grade', str(res.data))

    def test_second_reviewer_required(self):
        feature_id = self.ready()
        res = self.alice_client.post(f'/api/team/features/{feature_id}/certify/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('second reviewer', str(res.data))
        res = self.bob_client.post(f'/api/team/features/{feature_id}/certify/')
        self.assertEqual(res.status_code, 200, res.data)
        f = Feature.objects.get(pk=feature_id)
        self.assertEqual((f.status, f.certified_by), ('certified', self.bob))
        self.assertIsNotNone(f.last_verified_at)

    def test_submitter_cannot_certify_either(self):
        feature_id = self.capture().data['id']
        self.upload(feature_id)
        self.bob_client.post(f'/api/team/features/{feature_id}/submit/')
        self.assertEqual(self.bob_client.post(f'/api/team/features/{feature_id}/certify/').status_code, 400)
        carol, carol_client = self.member('carol')
        self.assertEqual(carol_client.post(f'/api/team/features/{feature_id}/certify/').status_code, 200)

    def test_one_reviewer_when_turned_off(self):
        feature_id = self.ready()
        with mock.patch.object(content, 'rules', return_value=rules_with(second_reviewer_required=False)):
            self.assertEqual(self.alice_client.post(f'/api/team/features/{feature_id}/certify/').status_code, 200)

    def test_certifying_needs_a_photo_and_permission(self):
        feature_id = self.capture().data['id']
        res = self.bob_client.post(f'/api/team/features/{feature_id}/certify/')
        self.assertIn('photo', str(res.data))
        self.upload(feature_id)
        self.bob.groups.get(name=TRAIL_TEAM_GROUP).permissions.remove(
            *self.bob.groups.get().permissions.filter(codename='certify_feature'))
        bob = User.objects.get(pk=self.bob.pk)
        client = APIClient()
        client.force_authenticate(bob)
        res = client.post(f'/api/team/features/{feature_id}/certify/')
        self.assertIn('permission', str(res.data))

    def test_drafts_go_live_only_when_certified(self):
        feature_id = self.ready()
        trail_url = f'/api/trails/{self.trail.id}/'
        self.assertEqual(self.rider_client.get(trail_url).data['features'], [])
        self.bob_client.post(f'/api/team/features/{feature_id}/certify/')
        self.assertEqual([f['id'] for f in self.rider_client.get(trail_url).data['features']], [feature_id])

    def test_certified_grade_is_locked(self):
        feature_id = self.ready()
        self.bob_client.post(f'/api/team/features/{feature_id}/certify/')
        res = self.alice_client.patch(f'/api/team/features/{feature_id}/', {'grade': 6}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.alice_client.patch(f'/api/team/features/{feature_id}/', {'how_to_ride': 'Speed, then pop.'},
                                      format='json')
        self.assertEqual(res.status_code, 200)


class ChangedAndClosedTests(TeamTestCase):
    def certified(self):
        feature_id = self.ready()
        self.bob_client.post(f'/api/team/features/{feature_id}/certify/')
        return feature_id

    def test_changed_feature_is_regraded_and_recertified(self):
        feature_id = self.certified()
        res = self.alice_client.post(f'/api/team/features/{feature_id}/flag/', {'status': 'changed'}, format='json')
        self.assertEqual(res.data['status'], 'changed')
        self.assertTrue(Feature.objects.live().filter(pk=feature_id).exists())  # still shown, with a notice
        self.assertEqual(self.alice_client.patch(f'/api/team/features/{feature_id}/', {'grade': 4},
                                                 format='json').status_code, 200)
        self.alice_client.post(f'/api/team/features/{feature_id}/submit/')
        self.assertEqual(self.alice_client.post(f'/api/team/features/{feature_id}/certify/').status_code, 400)
        self.assertEqual(self.bob_client.post(f'/api/team/features/{feature_id}/certify/').data['grade'], 4)

    def test_closed_feature_is_hidden_and_can_reopen(self):
        feature_id = self.certified()
        self.alice_client.post(f'/api/team/features/{feature_id}/flag/', {'status': 'closed'}, format='json')
        self.assertFalse(Feature.objects.live().filter(pk=feature_id).exists())
        self.assertEqual(self.alice_client.post(f'/api/team/features/{feature_id}/verify/').status_code, 400)
        res = self.alice_client.post(f'/api/team/features/{feature_id}/reopen/')
        self.assertEqual(res.data['status'], 'draft')

    def test_only_certified_features_flag_as_changed(self):
        feature_id = self.capture().data['id']
        res = self.alice_client.post(f'/api/team/features/{feature_id}/flag/', {'status': 'changed'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_not_recently_verified(self):
        feature_id = self.certified()
        feature = Feature.objects.get(pk=feature_id)
        self.assertFalse(certification.is_stale(feature))
        Feature.objects.filter(pk=feature_id).update(last_verified_at=timezone.now() - timedelta(days=370))
        feature.refresh_from_db()
        self.assertTrue(certification.is_stale(feature))
        self.assertEqual([f['id'] for f in self.alice_client.get('/api/team/features/').data['stale']], [feature_id])
        self.alice_client.post(f'/api/team/features/{feature_id}/verify/')
        feature.refresh_from_db()
        self.assertFalse(certification.is_stale(feature))
        with mock.patch.object(content, 'rules', return_value=rules_with(stale_after_months=1)):
            Feature.objects.filter(pk=feature_id).update(last_verified_at=timezone.now() - timedelta(days=40))
            feature.refresh_from_db()
            self.assertTrue(certification.is_stale(feature))

    def test_rider_reports_go_to_the_queue(self):
        feature_id = self.certified()
        res = self.rider_client.post(f'/api/features/{feature_id}/report/', {'note': 'Lip washed out'},
                                     format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.rider_client.post(f'/api/features/{feature_id}/report/', {'note': 'Landing too'}, format='json')
        report = FeatureReport.objects.get()  # a second tap adds to the open report
        self.assertEqual(report.note, 'Lip washed out\nLanding too')
        self.assertEqual(Feature.objects.get(pk=feature_id).status, 'certified')  # the team decides
        queue = self.alice_client.get('/api/team/features/').data
        self.assertEqual(queue['counts']['open_reports'], 1)
        self.assertEqual(queue['reported'][0]['open_reports'][0]['note'], report.note)
        self.alice_client.post(f'/api/team/reports/{report.id}/resolve/', {'status': 'dismissed'}, format='json')
        self.assertEqual(self.alice_client.get('/api/team/features/').data['counts']['open_reports'], 0)

    def test_riders_cannot_report_drafts(self):
        feature_id = self.capture().data['id']
        self.assertEqual(self.rider_client.post(f'/api/features/{feature_id}/report/').status_code, 404)

    def test_queue(self):
        submitted = self.ready()
        unsubmitted = self.capture(at=15).data['id']
        queue = self.bob_client.get('/api/team/features/').data
        self.assertEqual([f['id'] for f in queue['awaiting_review']], [submitted])
        self.assertTrue(queue['awaiting_review'][0]['can_certify'])
        self.assertEqual([f['id'] for f in queue['drafts']], [unsubmitted])


class LadderAndAdminTests(TeamTestCase):
    def test_ladder_warnings_for_missing_rungs(self):
        for grade in (1, 2, 5):
            Feature.objects.create(trail=self.trail, name=f'Drop {grade}', type='drop', grade=grade, lat=45,
                                   lng=-122, status='certified')
        Feature.objects.create(trail=self.trail, name='Ungraded', type='jump', lat=45, lng=-122)
        messages = [w['message'] for w in certification.ladder_warnings(self.system)]
        self.assertIn('Drop: no grade 3, 4 between 2 and 5. Riders will stall at 2.', messages)
        self.assertIn('Ungraded has no grade yet.', messages)
        Feature.objects.filter(grade=1).delete()
        messages = [w['message'] for w in certification.ladder_warnings(self.system)]
        self.assertIn('Drop: the ladder starts at grade 2. Riders new to drops only get grade 1 suggested.', messages)

    def test_bulk_trail_view_reorders(self):
        a = Feature.objects.create(trail=self.trail, name='A', type='drop', grade=1, lat=45, lng=-122, position=1)
        b = Feature.objects.create(trail=self.trail, name='B', type='drop', grade=3, lat=45, lng=-122, position=2)
        admin = User.objects.create_superuser(username='boss', email='boss@example.com', password='x')
        self.client.force_login(admin)
        url = f'/admin/trails/trail/{self.trail.id}/features/'
        res = self.client.get(url)
        self.assertContains(res, 'Riding order')
        self.assertContains(res, 'no grade 2')
        self.client.post(url, {'move': f'{b.id}:up'})
        self.assertEqual(list(self.trail.features.order_by('position').values_list('name', flat=True)), ['B', 'A'])

    def test_admin_certify_enforces_second_reviewer(self):
        feature_id = self.ready()
        self.alice.is_staff = True
        self.alice.save()
        self.client.force_login(self.alice)
        res = self.client.post('/admin/trails/feature/', {'action': 'certify', '_selected_action': [feature_id]},
                               follow=True)
        self.assertContains(res, 'second reviewer')
        self.assertEqual(Feature.objects.get(pk=feature_id).status, 'draft')

    def test_feature_form_shows_guidelines(self):
        feature_id = self.capture().data['id']
        admin = User.objects.create_superuser(username='boss', email='boss@example.com', password='x')
        self.client.force_login(admin)
        res = self.client.get(f'/admin/trails/feature/{feature_id}/change/')
        self.assertContains(res, 'Next Line grading guidelines')
        self.assertContains(res, 'Small drops')  # the skill-tag picker
