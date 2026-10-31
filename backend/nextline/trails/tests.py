from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from rides.tests import descent_trail, make_track, second_lap, upload

from .models import Feature, FeatureProgress, Trail

User = get_user_model()


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
        lat, lng = trail.path[10]
        feature = Feature.objects.create(trail=trail, name='Step-down', lat=lat, lng=lng)
        FeatureProgress.objects.create(user=self.user, feature=feature, status='cleaned', clean_count=3)
        res = self.client.get(f'/api/trails/{trail.id}/')
        self.assertEqual(res.data['features'][0]['status'], 'cleaned')
        self.assertEqual(res.data['features'][0]['clean_count'], 3)
        self.assertEqual(res.data['cleaned_count'], 1)
        self.assertEqual(len(res.data['efforts']), 1)
        self.assertEqual(res.data['direction'], 'descent')

    def test_pin_feature_on_trail(self):
        upload(self.client)
        trail = descent_trail()
        lat, lng = trail.path[5]
        res = self.client.post(f'/api/trails/{trail.id}/features/',
                               {'name': 'Rock garden', 'kind': 'rock_garden', 'lat': lat, 'lng': lng}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['status'], 'locked')
        far = self.client.post(f'/api/trails/{trail.id}/features/',
                               {'name': 'Nope', 'lat': lat + 0.01, 'lng': lng}, format='json')
        self.assertEqual(far.status_code, 400)

    def test_set_feature_progress(self):
        upload(self.client)
        trail = descent_trail()
        lat, lng = trail.path[5]
        feature = Feature.objects.create(trail=trail, name='Gap', lat=lat, lng=lng, created_by=self.user)
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
        alice_ride = upload(self.alice_client, make_track(descent_speed=6)).data
        bob_ride = upload(self.bob_client, make_track(descent_speed=7.5)).data
        self.trail = Trail.objects.get(owner=self.alice, direction='descent')
        self.copy = Trail.objects.get(owner=self.bob, direction='descent')
        lat, lng = self.trail.path[10]
        self.drop = Feature.objects.create(trail=self.trail, name='3 ft drop', lat=lat, lng=lng, created_by=self.alice)
        self.alice_client.post(f"/api/rides/{alice_ride['id']}/checkin/", {'cleaned': [self.drop.id]}, format='json')
        # Bob pinned the same drop on his copy, plus a rock garden further down.
        self.bobs_drop = Feature.objects.create(trail=self.copy, name='Drop', lat=lat, lng=lng, created_by=self.bob)
        lat, lng = self.copy.path[40]
        self.rocks = Feature.objects.create(trail=self.copy, name='Rock garden', lat=lat, lng=lng, created_by=self.bob)
        self.bob_client.post(f"/api/rides/{bob_ride['id']}/checkin/",
                             {'cleaned': [self.bobs_drop.id], 'almost': [self.rocks.id]}, format='json')
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

        # Bob's progress on his copy of the drop now sits on the shared drop.
        drop = FeatureProgress.objects.get(user=self.bob, feature=self.drop)
        self.assertEqual(drop.status, 'cleaned')
        self.assertFalse(Feature.objects.filter(pk=self.bobs_drop.pk).exists())
        self.rocks.refresh_from_db()
        self.assertEqual(self.rocks.trail, self.trail)
        from rides.models import Ride
        self.assertEqual(Ride.objects.get(pk=self.bob_ride_id).cleaned_features, [self.drop.id])

        # Riders' pins wait for approval once the trail is shared: Bob sees only his own until then.
        self.assertEqual(result['features_pending'], 2)
        detail = self.bob_client.get(f'/api/trails/{self.trail.id}/').data
        self.assertEqual([f['name'] for f in detail['features']], ['Rock garden'])
        Feature.objects.filter(trail=self.trail).update(approved=True)

        # Once approved, Bob sees both features with his statuses.
        detail = self.bob_client.get(f'/api/trails/{self.trail.id}/').data
        self.assertEqual({f['name']: f['status'] for f in detail['features']},
                         {'3 ft drop': 'cleaned', 'Rock garden': 'almost'})

    def test_new_riders_ride_the_shared_trail(self):
        from .sharing import promote
        promote(self.trail)
        Feature.objects.filter(trail=self.trail).update(approved=True)
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


class FeatureApprovalTests(TestCase):
    def setUp(self):
        self.rider = User.objects.create_user(username='rider', email='r@example.com', password='x')
        self.other = User.objects.create_user(username='other', email='o@example.com', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.rider)
        self.other_client = APIClient()
        self.other_client.force_authenticate(self.other)
        self.shared = Trail.objects.create(name='Rattlesnake DH', difficulty='black', start_lat=0, start_lng=0,
                                           end_lat=0, end_lng=0.01, length_m=1100,
                                           path=[[0, i * 0.0005] for i in range(21)])

    def pin(self, client, trail, name='Rock garden'):
        return client.post(f'/api/trails/{trail.id}/features/', {'name': name, 'lat': 0, 'lng': 0.005},
                           format='json').data

    def test_rider_pin_on_shared_trail_waits_for_approval(self):
        pinned = self.pin(self.client, self.shared)
        self.assertFalse(pinned['approved'])
        self.assertEqual([f['name'] for f in self.client.get(f'/api/trails/{self.shared.id}/').data['features']],
                         ['Rock garden'])
        self.assertEqual(self.other_client.get(f'/api/trails/{self.shared.id}/').data['features'], [])
        # Others can't mark it either.
        res = self.other_client.put(f"/api/features/{pinned['id']}/progress/", {'status': 'cleaned'}, format='json')
        self.assertEqual(res.status_code, 404)

    def test_pending_feature_earns_no_points_until_approved(self):
        from rides.scoring import level_points
        pinned = self.pin(self.client, self.shared)
        self.client.put(f"/api/features/{pinned['id']}/progress/", {'status': 'cleaned'}, format='json')
        self.assertEqual(level_points(self.rider)[1]['features'], 0)
        Feature.objects.filter(pk=pinned['id']).update(approved=True)
        self.assertEqual(level_points(self.rider)[1]['features'], 100)  # 25 x black

    def test_pins_on_your_own_trail_and_by_staff_are_live(self):
        upload(self.client)
        own = Trail.objects.get(owner=self.rider, direction='descent')
        lat, lng = own.path[5]
        res = self.client.post(f'/api/trails/{own.id}/features/', {'name': 'Drop', 'lat': lat, 'lng': lng},
                               format='json')
        self.assertTrue(res.data['approved'])
        staff = User.objects.create_user(username='staff', email='s@example.com', password='x', is_staff=True)
        staff_client = APIClient()
        staff_client.force_authenticate(staff)
        self.assertTrue(self.pin(staff_client, self.shared)['approved'])
        self.assertEqual(len(self.other_client.get(f'/api/trails/{self.shared.id}/').data['features']), 1)

    def test_admin_approve_and_merge(self):
        staff = User.objects.create_superuser(username='boss', email='boss@example.com', password='x')
        original = Feature.objects.create(trail=self.shared, name='Rock garden', lat=0, lng=0.005, created_by=staff)
        duplicate = self.pin(self.client, self.shared, name='Rocks')
        self.client.put(f"/api/features/{duplicate['id']}/progress/", {'status': 'cleaned'}, format='json')
        extra = self.pin(self.client, self.shared, name='Step-up')

        self.client.force_login(staff)  # the Django test client, for the admin
        self.client.post('/admin/trails/feature/', {'action': 'merge_into_nearest', '_selected_action': [duplicate['id']]})
        self.assertFalse(Feature.objects.filter(pk=duplicate['id']).exists())
        self.assertEqual(FeatureProgress.objects.get(user=self.rider, feature=original).status, 'cleaned')

        self.client.post('/admin/trails/feature/', {'action': 'approve', '_selected_action': [extra['id']]})
        self.assertTrue(Feature.objects.get(pk=extra['id']).approved)
