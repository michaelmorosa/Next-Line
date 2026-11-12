from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from rides.tests import descent_trail, make_track, second_lap, upload

from .apps import TRAIL_TEAM_GROUP
from .models import Feature, FeatureLog, Trail, is_trail_team

User = get_user_model()


def team_member(username='team'):
    user = User.objects.create_user(username=username, email=f'{username}@example.com', password='x')
    user.groups.add(Group.objects.get(name=TRAIL_TEAM_GROUP))
    return User.objects.get(pk=user.pk)  # fresh, so permissions aren't cached


def log(user, feature, outcome='cleaned', times=1):
    for _ in range(times):
        FeatureLog.objects.create(user=user, feature=feature, outcome=outcome, ridden_on=date.today(),
                                  grade_at_log=feature.grade)


class TrailApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rider', email='r@example.com', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_auto_trail_shows_after_second_ride(self):
        upload(self.client)
        self.assertEqual(self.client.get('/api/trails/').data, [])
        upload(self.client, make_track(descent_speed=7))
        trails = self.client.get('/api/trails/').data
        self.assertEqual(sorted(t['direction'] for t in trails), ['climb', 'descent'])
        trails = [t for t in trails if t['direction'] == 'descent']
        self.assertEqual(trails[0]['ride_count'], 2)
        self.assertEqual((trails[0]['laps'], trails[0]['clean_laps']), (2, 2))
        self.assertAlmostEqual(trails[0]['best_s'], 257, delta=15)

    def test_two_laps_in_one_ride_show_the_trail(self):
        upload(self.client, second_lap(make_track()))
        trails = self.client.get('/api/trails/').data  # the climb was ridden once, so only the descent shows
        self.assertEqual((trails[0]['laps'], trails[0]['ride_count']), (2, 1))

    def test_detail_has_features_with_my_status(self):
        upload(self.client)
        trail = descent_trail()
        Trail.objects.filter(pk=trail.pk).update(owner=None)  # features only show on shared trails
        lat, lng = trail.path[10]
        feature = Feature.objects.create(trail=trail, name='Step-down', lat=lat, lng=lng, status='certified', grade=3)
        log(self.user, feature, times=3)
        res = self.client.get(f'/api/trails/{trail.id}/')
        self.assertEqual(res.data['features'][0]['status'], 'cleaned')
        self.assertEqual(res.data['features'][0]['clean_count'], 3)
        self.assertEqual(res.data['cleaned_count'], 1)
        self.assertEqual(len(res.data['efforts']), 1)
        self.assertEqual(res.data['direction'], 'descent')

    def test_only_the_trail_team_adds_features(self):
        upload(self.client)
        trail = descent_trail()
        Trail.objects.filter(pk=trail.pk).update(owner=None)
        lat, lng = trail.path[5]
        body = {'name': 'Rock garden', 'type': 'rock_garden', 'lat': lat, 'lng': lng}
        self.assertEqual(self.client.post(f'/api/trails/{trail.id}/features/', body, format='json').status_code, 403)
        team = APIClient()
        team.force_authenticate(team_member())
        res = team.post(f'/api/trails/{trail.id}/features/', body, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data['certification'], res.data['position']), ('draft', 1))
        # Drafts are team-only.
        self.assertEqual(self.client.get(f'/api/trails/{trail.id}/').data['features'], [])
        far = team.post(f'/api/trails/{trail.id}/features/', {'name': 'Nope', 'lat': lat + 0.01, 'lng': lng},
                        format='json')
        self.assertEqual(far.status_code, 400)

    def test_set_feature_progress(self):
        upload(self.client)
        trail = descent_trail()
        Trail.objects.filter(pk=trail.pk).update(owner=None)
        lat, lng = trail.path[5]
        feature = Feature.objects.create(trail=trail, name='Gap', lat=lat, lng=lng, status='certified', grade=2)
        res = self.client.put(f'/api/features/{feature.id}/progress/', {'status': 'cleaned'}, format='json')
        self.assertEqual(res.data['status'], 'cleaned')
        self.assertEqual(res.data['clean_count'], 1)
        self.assertIsNotNone(res.data['first_cleaned_at'])

    def test_rename_own_auto_trail_only(self):
        upload(self.client)
        mine = descent_trail()
        res = self.client.patch(f'/api/trails/{mine.id}/', {'name': 'Rattlesnake DH', 'difficulty': 'black'},
                                format='json')
        self.assertEqual(res.status_code, 200, res.data)
        mine.refresh_from_db()
        self.assertEqual((mine.name, mine.difficulty), ('Rattlesnake DH', 'black'))
        shared = Trail.objects.create(name='Shared', start_lat=0, start_lng=0, end_lat=0, end_lng=0, length_m=1)
        self.assertEqual(self.client.patch(f'/api/trails/{shared.id}/', {'name': 'x'}, format='json').status_code, 403)

    def test_cannot_see_other_riders_auto_trails(self):
        upload(self.client)
        trail = descent_trail()
        other = APIClient()
        other.force_authenticate(User.objects.create_user(username='o', email='o@example.com', password='x'))
        self.assertEqual(other.get(f'/api/trails/{trail.id}/').status_code, 404)
        # And their own ride on the same descent gets its own auto trail.
        upload(other)
        self.assertEqual(Trail.objects.filter(direction='descent').count(), 2)


class PromoteTrailTests(TestCase):
    def rider(self, name):
        user = User.objects.create_user(username=name, email=f'{name}@example.com', password='x')
        client = APIClient()
        client.force_authenticate(user)
        return user, client

    def setUp(self):
        self.alice, self.alice_client = self.rider('alice')
        self.bob, self.bob_client = self.rider('bob')
        upload(self.alice_client, make_track(descent_speed=6))
        bob_ride = upload(self.bob_client, make_track(descent_speed=7.5)).data
        self.trail = Trail.objects.get(owner=self.alice, direction='descent')
        self.copy = Trail.objects.get(owner=self.bob, direction='descent')
        lat, lng = self.trail.path[10]
        # Features riders pinned on their own copies before certified features (now drafts), with their logs.
        self.drop = Feature.objects.create(trail=self.trail, name='3 ft drop', lat=lat, lng=lng, created_by=self.alice)
        log(self.alice, self.drop)
        self.bobs_drop = Feature.objects.create(trail=self.copy, name='Drop', lat=lat, lng=lng, created_by=self.bob)
        lat, lng = self.copy.path[40]
        self.rocks = Feature.objects.create(trail=self.copy, name='Rock garden', lat=lat, lng=lng, created_by=self.bob,
                                            position=2)
        log(self.bob, self.bobs_drop)
        log(self.bob, self.rocks, 'sketchy')
        from rides.models import Ride
        Ride.objects.filter(pk=bob_ride['id']).update(cleaned_features=[self.bobs_drop.id])
        self.bob_ride_id = bob_ride['id']

    def test_promote_merges_copies(self):
        from .sharing import promote
        result = promote(self.trail)
        self.assertEqual((result['copies'], result['riders'], result['features_moved'], result['features_merged']),
                         (1, 1, 1, 1))
        self.trail.refresh_from_db()
        self.assertIsNone(self.trail.owner)
        self.assertFalse(Trail.objects.filter(pk=self.copy.pk).exists())
        self.assertEqual(self.trail.efforts.filter(user=self.bob).count(), 1)

        # Bob's log on his copy of the drop now sits on the shared drop.
        self.assertTrue(FeatureLog.objects.filter(user=self.bob, feature=self.drop, outcome='cleaned').exists())
        self.assertFalse(Feature.objects.filter(pk=self.bobs_drop.pk).exists())
        self.rocks.refresh_from_db()
        self.assertEqual(self.rocks.trail, self.trail)
        from rides.models import Ride
        self.assertEqual(Ride.objects.get(pk=self.bob_ride_id).cleaned_features, [self.drop.id])

        # Moved features are drafts: riders see none until the team certifies them.
        self.assertEqual(self.bob_client.get(f'/api/trails/{self.trail.id}/').data['features'], [])
        Feature.objects.filter(trail=self.trail).update(status='certified', grade=3)
        detail = self.bob_client.get(f'/api/trails/{self.trail.id}/').data
        self.assertEqual({f['name']: f['status'] for f in detail['features']},
                         {'3 ft drop': 'cleaned', 'Rock garden': 'almost'})

    def test_new_riders_ride_the_shared_trail(self):
        from .sharing import promote
        promote(self.trail)
        Feature.objects.filter(trail=self.trail).update(status='certified', grade=3)
        carol, carol_client = self.rider('carol')
        upload(carol_client)
        self.assertFalse(Trail.objects.filter(owner=carol, direction='descent').exists())
        self.assertEqual(self.trail.efforts.filter(user=carol).count(), 1)
        names = [f['name'] for f in carol_client.get(f'/api/trails/{self.trail.id}/').data['features']]
        self.assertEqual(names, ['3 ft drop', 'Rock garden'])

    def test_lap_counted_on_two_copies_is_kept_once(self):
        from .sharing import promote
        # Alice somehow has a second private copy, and a ride timed on both.
        Trail.objects.create(name='Dup', owner=self.alice, is_auto=True, start_lat=self.trail.start_lat,
                             start_lng=self.trail.start_lng, end_lat=self.trail.end_lat, end_lng=self.trail.end_lng,
                             length_m=self.trail.length_m, path=self.trail.path)
        upload(self.alice_client, make_track(descent_speed=7), started_at=timezone.now())  # after the setUp ride
        promote(self.trail)
        laps = self.trail.efforts.filter(user=self.alice).order_by('started_at')
        self.assertEqual(laps.count(), 2)
        self.assertEqual([e.is_pr for e in laps], [False, True])

    def test_admin_action(self):
        admin = User.objects.create_superuser(username='boss', email='boss@example.com', password='x')
        self.client.force_login(admin)
        res = self.client.post('/admin/trails/trail/', {
            'action': 'make_shared', '_selected_action': [self.trail.pk],
        }, follow=True)
        self.assertContains(res, 'is now shared')
        self.trail.refresh_from_db()
        self.assertIsNone(self.trail.owner)

    def test_other_directions_are_not_copies(self):
        from .sharing import find_copies
        self.assertEqual(find_copies(self.trail), [self.copy])


class FeatureVisibilityTests(TestCase):
    def setUp(self):
        self.rider = User.objects.create_user(username='rider', email='r@example.com', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.rider)
        self.shared = Trail.objects.create(name='Rattlesnake DH', difficulty='black', start_lat=0, start_lng=0,
                                           end_lat=0, end_lng=0.01, length_m=1100,
                                           path=[[0, i * 0.0005] for i in range(21)])

    def feature(self, name, status, position):
        return Feature.objects.create(trail=self.shared, name=name, lat=0, lng=0.0001 * position, status=status,
                                      grade=3, position=position)

    def test_riders_see_certified_and_changed_only(self):
        self.feature('Draft', 'draft', 1)
        self.feature('Live', 'certified', 3)
        self.feature('Rebuilt', 'changed', 2)
        self.feature('Gone', 'closed', 4)
        names = [f['name'] for f in self.client.get(f'/api/trails/{self.shared.id}/').data['features']]
        self.assertEqual(names, ['Rebuilt', 'Live'])  # in riding order
        team = APIClient()
        team.force_authenticate(team_member())
        self.assertEqual(len(team.get(f'/api/trails/{self.shared.id}/').data['features']), 4)

    def test_trail_team_membership(self):
        self.assertFalse(is_trail_team(self.rider))
        self.assertTrue(is_trail_team(team_member()))
        self.assertTrue(is_trail_team(User.objects.create_superuser(username='boss', email='b@example.com',
                                                                    password='x')))

    def test_admin_merge_moves_logs(self):
        staff = User.objects.create_superuser(username='boss', email='boss@example.com', password='x')
        original = self.feature('Rock garden', 'certified', 1)
        duplicate = self.feature('Rocks', 'draft', 2)
        log(self.rider, duplicate)
        self.client.force_login(staff)  # the Django test client, for the admin
        self.client.post('/admin/trails/feature/', {'action': 'merge_into_nearest', '_selected_action': [duplicate.id]})
        self.assertFalse(Feature.objects.filter(pk=duplicate.id).exists())
        self.assertTrue(FeatureLog.objects.filter(user=self.rider, feature=original).exists())

    def test_grading_guidelines_start_from_the_file(self):
        from .models import GradingGuidelines
        doc = GradingGuidelines.get()
        self.assertIn('Drops', doc.body)
        doc.body = 'Edited'
        doc.save()
        self.assertEqual(GradingGuidelines.get().body, 'Edited')
        self.assertEqual(GradingGuidelines.objects.count(), 1)


class ProgressToLogsMigrationTests(TransactionTestCase):
    """Migration 0007: old kinds map to the new types, features become numbered drafts, progress becomes logs."""
    before = [('trails', '0006_feature_ladders'), ('users', '0002_advanced_and_safety')]
    after = [('trails', '0007_progress_to_logs')]

    def test_migration(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        apps = executor.loader.project_state(self.before).apps
        user = apps.get_model('users', 'CustomUser').objects.create(username='r', email='r@example.com')
        trail = apps.get_model('trails', 'Trail').objects.create(
            name='T', start_lat=0, start_lng=0, end_lat=0, end_lng=0, length_m=1)
        Feature = apps.get_model('trails', 'Feature')
        berm = Feature.objects.create(trail=trail, name='Berm', type='berm', lat=0, lng=0, status='certified')
        gap = Feature.objects.create(trail=trail, name='Gap', type='gap', lat=0, lng=0)
        Progress = apps.get_model('trails', 'FeatureProgress')
        when = timezone.now()
        Progress.objects.create(user=user, feature=berm, status='cleaned', clean_count=3, first_cleaned_at=when,
                                note='Smooth')
        Progress.objects.create(user=user, feature=gap, status='almost')

        executor = MigrationExecutor(connection)
        executor.migrate(self.after)
        apps = executor.loader.project_state(self.after).apps
        Feature = apps.get_model('trails', 'Feature')
        berm, gap = Feature.objects.get(name='Berm'), Feature.objects.get(name='Gap')
        self.assertEqual((berm.type, berm.position, berm.status), ('corner', 1, 'draft'))
        self.assertEqual((gap.type, gap.position), ('jump', 2))
        logs = apps.get_model('trails', 'FeatureLog').objects.all()
        self.assertEqual(sorted(logs.values_list('outcome', flat=True)), ['cleaned'] * 3 + ['sketchy'])
        self.assertEqual(logs.filter(note='Smooth').count(), 1)

        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
