import math
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from trails.models import Feature, FeatureProgress, FeatureStatus, Trail

from . import analysis
from .models import CrashAlert, Ride, TrailEffort
from .tiers import TIERS

User = get_user_model()

ORIGIN = (34.0, -118.0)
M_PER_DEG_LAT = 111195
M_PER_DEG_LNG = M_PER_DEG_LAT * math.cos(math.radians(ORIGIN[0]))


def make_track(descent_speed=6.0, wobble=0.0, climb_s=600, descent_length=1800, drop=150, base_alt=500,
               climb_speed=2.5):
    """A climb north lasting `climb_s`, then a straight descent east. `wobble` swings descent speed up and down."""
    points = []
    lat, lng, alt = ORIGIN[0], ORIGIN[1], base_alt
    t = 0
    for _ in range(climb_s):
        lat += climb_speed / M_PER_DEG_LAT
        alt += drop / climb_s
        t += 1
        points.append([t, lat, lng, alt, climb_speed])
    covered = 0.0
    while covered < descent_length:
        speed = descent_speed + wobble * math.sin(t / 3)
        covered += speed
        lng += speed / M_PER_DEG_LNG
        t += 1
        points.append([t, lat, lng, base_alt + drop - drop * min(covered, descent_length) / descent_length, speed])
    return points


def upload(client, track=None, started_at=None, jumps=(), client_id=None):
    return client.post('/api/rides/', {
        'client_id': str(client_id or uuid.uuid4()),
        'started_at': (started_at or timezone.now() - timedelta(hours=2)).isoformat(),
        'elapsed_s': 900,
        'track': track if track is not None else make_track(),
        'jumps': list(jumps),
    }, format='json')


def descent_trail():
    return Trail.objects.get(direction='descent')


def laps_of(res, direction='descent'):
    return [e for e in res.data['efforts'] if e['trail_direction'] == direction]


def with_stall(points, at, seconds):
    """Insert a stop of `seconds` (speed 0, same spot) at index `at`, shifting the rest of the track later."""
    t0, lat, lng, alt, _ = points[at]
    stall = [[t0 + i + 1, lat, lng, alt, 0.0] for i in range(seconds)]
    rest = [[p[0] + seconds, *p[1:]] for p in points[at + 1:]]
    return points[:at + 1] + stall + rest


def second_lap(points, gap_s=1800):
    """The track followed by another run of its descent, after a shuttle back to the top."""
    descent = points[600:]
    shift = points[-1][0] + gap_s - descent[0][0]
    return points + [[p[0] + shift, *p[1:]] for p in descent]


def make_loop(laps=3, side_m=500, speed=5.0):
    """Flat square laps starting and finishing at ORIGIN."""
    points = []
    lat, lng = ORIGIN
    t = 0
    steps = int(side_m / speed)
    for _ in range(laps):
        for dlat, dlng in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            for _ in range(steps):
                lat += dlat * speed / M_PER_DEG_LAT
                lng += dlng * speed / M_PER_DEG_LNG
                t += 1
                points.append([t, lat, lng, 500, speed])
    return points


class AnalysisTests(TestCase):
    def test_elevation_ignores_gps_noise(self):
        climb, descent = analysis.elevation_totals([100, 101, 99, 100.5, 99.5, 100])
        self.assertEqual((climb, descent), (0, 0))
        climb, descent = analysis.elevation_totals([100, 110, 120, 105])
        self.assertEqual((climb, descent), (20, 15))

    def test_finds_the_descent_and_not_the_climb(self):
        points = analysis.clean_track(make_track())
        descents = analysis.find_descents(points)
        self.assertEqual(len(descents), 1)
        start, end = descents[0]
        self.assertAlmostEqual(points[start][0], 600, delta=10)
        self.assertAlmostEqual(points[end][0], 900, delta=10)

    def test_short_rise_does_not_split_a_descent(self):
        points = make_track()
        for p in points[700:705]:
            p[3] += 5
        descents = analysis.find_descents(analysis.clean_track(points))
        self.assertEqual(len(descents), 1)

    def test_steady_speed_flows_better_than_jerky(self):
        steady = analysis.flow_score(analysis.clean_track(make_track(wobble=0.3))[600:])
        jerky = analysis.flow_score(analysis.clean_track(make_track(wobble=4.0))[600:])
        self.assertGreater(steady, 90)
        self.assertLess(jerky, steady - 20)

    def test_gps_glitch_is_dropped(self):
        points = make_track()
        points[300][1] += 0.05  # 5 km away for one second
        cleaned = analysis.clean_track(points)
        self.assertEqual(len(cleaned), len(points) - 1)
        self.assertLess(analysis.summarize(cleaned)['max_speed'], 10)

    def test_stops_are_not_moving_time(self):
        points = analysis.clean_track(make_track())
        stopped = [[p[0] + 1000, p[1], p[2], p[3], 0.0] for p in points[-60:]]
        self.assertAlmostEqual(analysis.moving_time(points + stopped), analysis.moving_time(points), delta=1)

    def test_touchdown_is_a_short_stall_then_riding_on(self):
        points = analysis.clean_track(with_stall(make_track(), 750, 4))
        self.assertEqual(analysis.find_touchdowns(points), [752])  # first stopped point

    def test_long_stop_is_a_rest_not_a_touchdown(self):
        points = analysis.clean_track(with_stall(make_track(), 750, 40))
        self.assertEqual(analysis.find_touchdowns(points), [])

    def test_stopping_at_the_bottom_is_not_a_touchdown(self):
        points = make_track()
        points += [[points[-1][0] + i + 1, *points[-1][1:4], 0.0] for i in range(10)]
        self.assertEqual(analysis.find_touchdowns(analysis.clean_track(points)), [])

    def test_rest_splits_the_nonstop_climb(self):
        points = analysis.clean_track(with_stall(make_track(), 300, 40))
        alts = analysis.smoothed_altitudes(points)
        stamina = analysis.climbing_stamina(points, alts, analysis.find_climbs(points, alts))
        self.assertEqual(stamina['climb_rests'], 1)
        self.assertAlmostEqual(stamina['longest_nonstop_climb_m'], 75, delta=10)

    def test_fading_on_the_climb_lowers_pace_held(self):
        points = make_track()
        # Second half of the climb at half the pace: same gain, twice the time.
        slow = []
        t = points[299][0]
        for p in points[300:600]:
            t += 2
            slow.append([t, p[1], p[2], p[3], 1.25])
        rest = [[p[0] + 300, *p[1:]] for p in points[600:]]
        points = analysis.clean_track(points[:300] + slow + rest)
        alts = analysis.smoothed_altitudes(points)
        stamina = analysis.climbing_stamina(points, alts, analysis.find_climbs(points, alts))
        self.assertLess(stamina['climb_pace_held'], 80)

    def test_position_at_interpolates(self):
        points = [[0, 10.0, 20.0, None, 0], [10, 11.0, 22.0, None, 0]]
        self.assertEqual(analysis.position_at(points, 5), (10.5, 21.0))
        self.assertIsNone(analysis.position_at(points, 11))


class RideApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rider', email='r@example.com', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_upload_scores_the_ride_and_creates_an_auto_trail(self):
        res = upload(self.client, jumps=[{'t': 700, 'airtime_s': 0.5}, {'t': 710, 'airtime_s': 0.05}])
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['jump_count'], 1)  # 0.05 s is noise
        self.assertEqual(res.data['biggest_air_s'], 0.5)
        self.assertIsNotNone(res.data['jumps'][0]['lat'])
        self.assertAlmostEqual(res.data['descent_m'], 150, delta=10)
        self.assertGreater(res.data['flow_score'], 90)
        self.assertEqual(len(laps_of(res)), 1)
        trail = descent_trail()
        self.assertTrue(trail.is_auto)
        self.assertEqual(trail.owner, self.user)
        self.assertEqual(res.data['title'], trail.name)  # named after the descent, not the longer climb

    def test_repeat_ride_matches_the_trail_and_sets_a_pr(self):
        upload(self.client, make_track(descent_speed=6), started_at=timezone.now() - timedelta(days=3))
        res = upload(self.client, make_track(descent_speed=7.5))
        self.assertEqual(Trail.objects.filter(direction='descent').count(), 1)
        effort = laps_of(res)[0]
        self.assertTrue(effort['is_pr'])
        self.assertAlmostEqual(effort['previous_best_s'], 300, delta=15)
        self.assertEqual(res.data['pr_count'], 1)
        slower = upload(self.client, make_track(descent_speed=5), started_at=timezone.now())
        self.assertFalse(laps_of(slower)[0]['is_pr'])

    def test_touchdowns_counted_per_lap(self):
        track = with_stall(make_track(), 750, 4)   # foot down on the descent
        track = with_stall(track, 300, 3)          # and one on the climb
        res = upload(self.client, track)
        self.assertEqual(res.data['touchdowns_detected'], 2)
        self.assertEqual(laps_of(res)[0]['touchdowns'], 1)
        self.assertEqual(laps_of(res, 'climb')[0]['touchdowns'], 1)

    def test_touchdowns_on_flats_between_segments_do_not_count(self):
        flat = [[p[0] + 2000, p[1] + 0.02, p[2], 500, 5.0] for p in make_loop(laps=1)]
        res = upload(self.client, make_track() + with_stall(flat, 100, 4))
        self.assertEqual(res.data['touchdowns_detected'], 0)

    def test_repeat_descents_are_laps(self):
        res = upload(self.client, second_lap(make_track()))
        # The shuttle back up (a 150 m jump over a GPS gap) is not a climb.
        self.assertEqual(Trail.objects.filter(direction='climb').count(), 1)
        self.assertEqual(Trail.objects.filter(direction='descent').count(), 1)
        self.assertEqual(res.data['lap_count'], 3)
        self.assertEqual(res.data['laps'][0], {
            'trail': descent_trail().id, 'trail_name': descent_trail().name, 'direction': 'descent',
            'laps': 2, 'clean_laps': 2,
        })
        self.assertIsNotNone(laps_of(res)[1]['previous_best_s'])  # lap 2 is timed against lap 1

    def test_loop_trail_counts_full_laps(self):
        Trail.objects.create(name='Pump loop', start_lat=ORIGIN[0], start_lng=ORIGIN[1], end_lat=ORIGIN[0],
                             end_lng=ORIGIN[1], length_m=2000)
        res = upload(self.client, make_loop(laps=3))
        self.assertEqual(res.data['laps'][0]['trail_name'], 'Pump loop')
        self.assertEqual(res.data['laps'][0]['laps'], 3)
        for effort in res.data['efforts']:
            self.assertAlmostEqual(effort['elapsed_s'], 400, delta=20)

    def test_partial_lap_is_not_counted(self):
        Trail.objects.create(name='Pump loop', start_lat=ORIGIN[0], start_lng=ORIGIN[1], end_lat=ORIGIN[0],
                             end_lng=ORIGIN[1], length_m=2000)
        track = make_loop(laps=2)
        res = upload(self.client, track[:len(track) * 3 // 4])  # quit halfway round lap 2
        self.assertEqual(res.data['lap_count'], 1)

    def test_climb_is_timed_with_a_climb_rate(self):
        res = upload(self.client)
        climb = laps_of(res, 'climb')[0]
        self.assertTrue(climb['trail_name'].startswith('Unnamed climb'))
        self.assertIsNone(climb['flow_score'])
        self.assertAlmostEqual(climb['climb_rate'], 900, delta=60)  # 150 m in 10 minutes
        self.assertAlmostEqual(res.data['climb_time_s'], 600, delta=30)
        self.assertAlmostEqual(res.data['climb_rate'], 900, delta=60)
        self.assertAlmostEqual(res.data['longest_nonstop_climb_m'], 150, delta=10)
        self.assertEqual(res.data['climb_rests'], 0)
        self.assertAlmostEqual(res.data['climb_pace_held'], 100, delta=5)

    def test_faster_climb_is_a_climb_pr(self):
        upload(self.client, make_track(climb_s=600), started_at=timezone.now() - timedelta(days=2))
        res = upload(self.client, make_track(climb_s=500, climb_speed=3.0))  # same 1500 m, quicker
        self.assertEqual(Trail.objects.filter(direction='climb').count(), 1)
        self.assertTrue(laps_of(res, 'climb')[0]['is_pr'])
        self.assertEqual(res.data['climb_pr_count'], 1)

    def test_lift_is_not_a_climb(self):
        upload(self.client, make_track(climb_s=150))  # 150 m in 2.5 minutes: 3600 m/hour
        self.assertFalse(Trail.objects.filter(direction='climb').exists())

    def test_same_recording_uploaded_twice_is_saved_once(self):
        client_id = uuid.uuid4()
        first = upload(self.client, client_id=client_id)
        again = upload(self.client, client_id=client_id)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(first.data['id'], again.data['id'])
        self.assertEqual(Ride.objects.count(), 1)

    def test_rides_are_private(self):
        ride_id = upload(self.client).data['id']
        other = APIClient()
        other.force_authenticate(User.objects.create_user(username='other', email='o@example.com', password='x'))
        self.assertEqual(other.get(f'/api/rides/{ride_id}/').status_code, 404)
        self.assertEqual(other.get('/api/rides/').data, [])

    def test_rejects_malformed_track(self):
        res = upload(self.client, track=[[0, 'north', 1]])
        self.assertEqual(res.status_code, 400)

    def test_upload_requires_login(self):
        self.assertEqual(upload(APIClient()).status_code, 401)

    def test_speed_rank_against_other_riders(self):
        upload(self.client, make_track(descent_speed=6))
        trail = descent_trail()
        trail.owner = None  # make it a shared trail so others match it
        trail.save()
        for i, speed in enumerate([5, 5.5, 7, 8]):
            other = APIClient()
            other.force_authenticate(User.objects.create_user(username=f'o{i}', email=f'o{i}@example.com', password='x'))
            upload(other, make_track(descent_speed=speed))
        ride = Ride.objects.filter(user=self.user).get()
        res = self.client.get(f'/api/rides/{ride.id}/')
        self.assertEqual(res.data['speed_rank'], 60)  # 2 of 4 others faster: (2 + 1) / (4 + 1)


class CheckinTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rider', email='r@example.com', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.ride_id = upload(self.client).data['id']
        self.trail = descent_trail()
        lat, lng = self.trail.path[len(self.trail.path) // 2]
        self.drop = Feature.objects.create(trail=self.trail, name='3 ft drop', kind='drop', lat=lat, lng=lng)
        self.roots = Feature.objects.create(trail=self.trail, name='Roots', kind='roots', lat=lat, lng=lng)

    def checkin(self, **body):
        return self.client.post(f'/api/rides/{self.ride_id}/checkin/', body, format='json')

    def test_ride_lists_features_on_trails_ridden(self):
        res = self.client.get(f'/api/rides/{self.ride_id}/')
        self.assertEqual([f['name'] for f in res.data['features']], ['3 ft drop', 'Roots'])

    def test_checkin_marks_features(self):
        res = self.checkin(confidence=4, cleaned=[self.drop.id], almost=[self.roots.id])
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['confidence'], 4)
        drop = FeatureProgress.objects.get(feature=self.drop)
        self.assertEqual((drop.status, drop.clean_count), (FeatureStatus.CLEANED, 1))
        self.assertEqual(FeatureProgress.objects.get(feature=self.roots).status, FeatureStatus.ALMOST)

    def test_editing_checkin_does_not_double_count(self):
        self.checkin(cleaned=[self.drop.id])
        self.checkin(cleaned=[self.drop.id])
        self.assertEqual(FeatureProgress.objects.get(feature=self.drop).clean_count, 1)
        self.checkin(cleaned=[])
        drop = FeatureProgress.objects.get(feature=self.drop)
        self.assertEqual((drop.status, drop.clean_count), (FeatureStatus.ALMOST, 0))

    def test_rider_corrects_touchdowns(self):
        res = self.checkin(touchdowns=3)
        self.assertEqual((res.data['touchdowns'], res.data['touchdowns_detected']), (3, 0))
        res = self.checkin(touchdowns=None)
        self.assertEqual(res.data['touchdowns'], 0)  # back to the estimate
        self.assertEqual(self.checkin(touchdowns=-1).status_code, 400)

    def test_cannot_check_in_other_riders_private_features(self):
        other = User.objects.create_user(username='other', email='o@example.com', password='x')
        hidden = Trail.objects.create(name='Secret', owner=other, start_lat=0, start_lng=0, end_lat=0, end_lng=0,
                                      length_m=1)
        feature = Feature.objects.create(trail=hidden, name='x', lat=0, lng=0)
        self.assertEqual(self.checkin(cleaned=[feature.id]).status_code, 400)


class CrashAlertTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rider', email='r@example.com', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_without_contact(self):
        res = self.client.post('/api/crash-alerts/', {'lat': 34, 'lng': -118}, format='json')
        self.assertEqual(res.data, {'status': 'no_contact', 'sent': False})

    def test_without_twilio(self):
        self.user.crash_contact_phone = '+15555550123'
        self.user.save()
        res = self.client.post('/api/crash-alerts/', {}, format='json')
        self.assertEqual(res.data['status'], 'not_configured')

    @override_settings(TWILIO_ACCOUNT_SID='AC1', TWILIO_AUTH_TOKEN='t', TWILIO_FROM_NUMBER='+15555550000')
    def test_texts_the_contact(self):
        self.user.crash_contact_phone = '+15555550123'
        self.user.save()
        with patch('rides.alerts.send_text', return_value=True) as send:
            res = self.client.post('/api/crash-alerts/', {'lat': 34.1, 'lng': -118.2}, format='json')
        self.assertTrue(res.data['sent'])
        to, body = send.call_args.args
        self.assertEqual(to, '+15555550123')
        self.assertIn('34.100000,-118.200000', body)
        self.assertEqual(CrashAlert.objects.get().status, 'sent')


class ProgressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rider', email='r@example.com', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_empty(self):
        res = self.client.get('/api/progress/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['level']['points'], 0)
        self.assertEqual(res.data['level']['tier'], 'Beginner I')
        self.assertEqual(len(res.data['flow_weeks']), 8)
        self.assertIsNone(res.data['favorite_trail'])

    def test_level_and_trend_after_rides(self):
        now = timezone.now()
        upload(self.client, make_track(descent_speed=6), started_at=now - timedelta(days=40),
               jumps=[{'t': 700, 'airtime_s': 0.4}])
        upload(self.client, make_track(descent_speed=7), started_at=now - timedelta(days=7),
               jumps=[{'t': 700, 'airtime_s': 0.6}])
        upload(self.client, make_track(descent_speed=7.5), started_at=now - timedelta(hours=1))
        res = self.client.get('/api/progress/')
        level = res.data['level']
        self.assertGreater(level['points'], 0)
        self.assertGreater(level['gain_30d'], 0)
        self.assertIn(level['to_next'] + level['points'], [threshold for threshold, _, _ in TIERS])
        favorite = res.data['favorite_trail']
        self.assertEqual(len(favorite['efforts']), 3)
        self.assertLess(favorite['best_s'], favorite['first_s'])
        self.assertGreaterEqual(res.data['totals']['streak_weeks'], 1)
        self.assertIsNotNone(res.data['flow_weeks'][-1]['flow'])
        climbing = res.data['climbing']
        self.assertEqual(len(climbing['weeks']), 8)
        self.assertIsNotNone(climbing['weeks'][-1]['climb_rate'])
        self.assertAlmostEqual(climbing['longest_nonstop_m'], 150, delta=10)
        self.assertEqual(len(res.data['favorite_climb']['efforts']), 3)

    def test_climbing_raises_level(self):
        from .scoring import CLEAN_CLIMB_POINTS, CLIMB_RATE_POINTS_CAP, level_points
        upload(self.client)  # 150 m in 10 minutes, no foot down
        _, parts = level_points(self.user)
        clean = CLEAN_CLIMB_POINTS  # one unrated climb cleaned
        rate = CLIMB_RATE_POINTS_CAP * 900 / 1200
        nonstop = 75  # 150 m at half a point per metre
        self.assertAlmostEqual(parts['climbing'], clean + rate + nonstop, delta=12)

        climb = Trail.objects.filter(direction='climb')
        climb.update(difficulty='black')  # the rider's own rating: counts as blue
        self.assertAlmostEqual(level_points(self.user)[1]['climbing'] - parts['climbing'], clean * 1, delta=1)
        climb.update(owner=None)  # a shared black climb counts in full
        self.assertAlmostEqual(level_points(self.user)[1]['climbing'] - parts['climbing'], clean * 3, delta=1)

    def test_climbing_fitness_is_capped(self):
        from .scoring import CLIMB_RATE_POINTS_CAP, NONSTOP_POINTS_CAP, climbing_points
        Ride.objects.create(user=self.user, client_id=uuid.uuid4(), started_at=timezone.now(), elapsed_s=1,
                            climb_time_s=3600, climb_rate=1900, longest_nonstop_climb_m=1500)
        self.assertEqual(climbing_points(self.user, Ride.objects.filter(user=self.user)),
                         CLIMB_RATE_POINTS_CAP + NONSTOP_POINTS_CAP)

    def test_short_climb_burst_does_not_set_best_rate(self):
        from .scoring import climbing_points
        Ride.objects.create(user=self.user, client_id=uuid.uuid4(), started_at=timezone.now(), elapsed_s=1,
                            climb_time_s=60, climb_rate=1800)
        self.assertEqual(climbing_points(self.user, Ride.objects.filter(user=self.user)), 0)

    def big_air_points(self, airtime_s):
        """A ride whose only points are air: 400 per second of the biggest air."""
        Ride.objects.create(user=self.user, client_id=uuid.uuid4(), started_at=timezone.now(), elapsed_s=1,
                            biggest_air_s=airtime_s)

    def clean_features(self, difficulty, count, owner=None):
        trail = Trail.objects.create(name=f'{difficulty} trail', difficulty=difficulty, owner=owner, start_lat=0,
                                     start_lng=0, end_lat=0, end_lng=0, length_m=1)
        for i in range(count):
            feature = Feature.objects.create(trail=trail, name=f'f{i}', lat=0, lng=0)
            FeatureProgress.objects.create(user=self.user, feature=feature, status='cleaned', clean_count=1,
                                           first_cleaned_at=timezone.now())

    def ride_in_past_weeks(self, weeks):
        for w in range(1, weeks + 1):
            Ride.objects.create(user=self.user, client_id=uuid.uuid4(), elapsed_s=1,
                                started_at=timezone.now() - timedelta(weeks=w))

    def test_points_alone_do_not_unlock_a_tier(self):
        self.big_air_points(6.0)  # 2400 points: past Intermediate I's 2000
        data = self.client.get('/api/progress/').data
        level = data['level']
        self.assertEqual(level['tier'], 'Beginner III')
        self.assertEqual((level['next_tier'], level['to_next']), ('Intermediate I', 0))
        self.assertEqual(level['requirements'], [
            {'kind': 'features', 'difficulty': 'blue', 'label': '5 blue (or harder) features cleaned',
             'needed': 5, 'have': 0, 'met': False},
            {'kind': 'weeks', 'difficulty': None, 'label': '4 active weeks', 'needed': 4, 'have': 1, 'met': False},
        ])
        self.assertIn('Still needed: 5 blue (or harder) features cleaned (0/5)', data['next_milestone'])

        self.clean_features('blue', 5)
        self.ride_in_past_weeks(3)  # 4 active weeks with this one
        self.assertEqual(self.client.get('/api/progress/').data['level']['tier'], 'Intermediate I')

    def test_rider_rated_black_counts_as_blue(self):
        from .scoring import FEATURE_POINTS, level_points
        self.clean_features('black', 3, owner=self.user)
        self.assertEqual(level_points(self.user)[1]['features'], 3 * FEATURE_POINTS * 2)
        from .tiers import requirement_stats
        stats = requirement_stats(self.user)
        self.assertEqual((stats['features']['blue'], stats['features']['black']), (3, 0))

    def test_mastered_trails_by_difficulty(self):
        from .achievements import mastered_trail_counts
        self.clean_features('blue', 3)
        self.clean_features('black', 3, owner=self.user)  # rider-rated: counts as blue
        self.clean_features('black', 2)  # not mastered: needs 3 features
        self.assertEqual(mastered_trail_counts(self.user), {'any': 2, 'blue': 2, 'black': 0, 'double_black': 0})

    def test_active_weeks_count_distinct_weeks(self):
        from .tiers import active_weeks
        self.ride_in_past_weeks(3)
        Ride.objects.create(user=self.user, client_id=uuid.uuid4(), elapsed_s=1,
                            started_at=timezone.now() - timedelta(weeks=1, minutes=5))
        self.assertEqual(active_weeks(self.user), 3)

    def test_expert_is_a_long_way_off(self):
        self.assertEqual(TIERS[-1][:2], (16000, 'Expert'))
        self.assertEqual(TIERS[-1][2]['weeks'], 52)

    def test_only_best_ten_descents_score_speed(self):
        from .scoring import SPEED_POINTS_PER_MS, SPEED_TRAILS_COUNTED, level_points
        ride = Ride.objects.create(user=self.user, client_id=uuid.uuid4(), started_at=timezone.now(), elapsed_s=1)
        for i in range(SPEED_TRAILS_COUNTED + 5):
            trail = Trail.objects.create(name=f't{i}', start_lat=0, start_lng=0, end_lat=0, end_lng=0, length_m=1)
            TrailEffort.objects.create(ride=ride, trail=trail, user=self.user, start_t=0, elapsed_s=60, avg_speed=5,
                                       started_at=timezone.now())
        self.assertEqual(level_points(self.user)[1]['speed'], SPEED_TRAILS_COUNTED * SPEED_POINTS_PER_MS * 5)

    def test_achievements_are_earned_once(self):
        res = upload(self.client, jumps=[{'t': 700, 'airtime_s': 0.6}])
        keys = {a['key'] for a in res.data['new_achievements']}
        self.assertTrue({'first_ride', 'first_air', 'air_half', 'clean_climb'} <= keys)
        self.assertNotIn('air_one', keys)
        again = upload(self.client, jumps=[{'t': 700, 'airtime_s': 0.6}])
        self.assertNotIn('first_ride', {a['key'] for a in again.data['new_achievements']})
        listing = {a['key']: a for a in self.client.get('/api/progress/').data['achievements']}
        self.assertIsNotNone(listing['first_ride']['earned_at'])
        self.assertIsNone(listing['air_one']['earned_at'])

    def test_black_diamond_achievement_needs_a_shared_trail(self):
        from .achievements import award
        self.clean_features('black', 1, owner=self.user)
        self.assertNotIn('black_feature', award(self.user))
        self.clean_features('black', 1)
        self.assertIn('black_feature', award(self.user))

    def test_ride_shows_level_points_it_earned(self):
        upload(self.client, make_track(), started_at=timezone.now() - timedelta(days=2),
               jumps=[{'t': 700, 'airtime_s': 0.4}])
        res = upload(self.client, make_track(descent_speed=7.5), jumps=[{'t': 700, 'airtime_s': 0.6}])
        gain = res.data['level_gain']
        self.assertGreater(gain['points'], 0)
        self.assertEqual(gain['parts']['air'], round(400 * 0.2) + 1)  # 0.2 s more air, one more jump
        self.assertIn('Biggest air yet: 0.60 s', gain['highlights'])
        self.assertTrue(any(h.startswith('New PR on') for h in gain['highlights']))

    def test_cleaning_a_feature_shows_in_the_ride_gain(self):
        ride = upload(self.client).data
        trail = descent_trail()
        lat, lng = trail.path[5]
        feature = Feature.objects.create(trail=trail, name='Root staircase', lat=lat, lng=lng)
        res = self.client.post(f"/api/rides/{ride['id']}/checkin/", {'cleaned': [feature.id]}, format='json')
        self.assertEqual(res.data['level_gain']['parts']['features'], 25)
        self.assertIn('Cleaned Root staircase for the first time (+25)', res.data['level_gain']['highlights'])

    def test_suggestions_put_the_tier_requirement_first(self):
        self.big_air_points(6.0)
        upload(self.client)
        mine = descent_trail()
        Feature.objects.create(trail=mine, name='Easy drop', lat=mine.path[3][0], lng=mine.path[3][1])
        shared = Trail.objects.create(name='Rattlesnake DH', difficulty='black', start_lat=0, start_lng=0, end_lat=0,
                                      end_lng=0, length_m=1)
        rock = Feature.objects.create(trail=shared, name='Rock garden', lat=0, lng=0)
        suggestions = self.client.get('/api/progress/').data['suggestions']
        self.assertEqual(suggestions[0]['title'], 'Clean Rock garden')
        self.assertIn('counts toward Intermediate I', suggestions[0]['detail'])
        self.assertIn('Ride in 3 more weeks', [s['title'] for s in suggestions])
        self.assertEqual(suggestions[0]['points'], 100)
        self.assertIn('Clean Easy drop', [s['title'] for s in suggestions])
        self.assertEqual(rock.trail_id, suggestions[0]['trail'])

    def test_level_rules(self):
        rules = self.client.get('/api/level-rules/').data
        self.assertEqual(rules['tiers'][3]['requirements'], ['5 blue (or harder) features cleaned', '4 active weeks'])
        self.assertEqual(rules['tiers'][-1]['requirements'],
                         ['8 double-black features cleaned', '1 double-black trail mastered', '52 active weeks'])
        self.assertEqual(rules['rider_rated_max'], 'Blue')
        self.assertEqual([s['key'] for s in rules['sources']], ['features', 'speed', 'air', 'descent', 'climbing'])

    def test_streak_counts_consecutive_weeks(self):
        from .scoring import ride_streak
        today = timezone.localdate()
        for weeks_ago in (0, 1, 2, 4):
            Ride.objects.create(user=self.user, client_id=uuid.uuid4(), elapsed_s=1,
                                started_at=timezone.now() - timedelta(weeks=weeks_ago))
        self.assertEqual(ride_streak(self.user, today), 3)

    def test_efforts_are_kept_when_trail_list_reads_them(self):
        upload(self.client)
        upload(self.client)
        self.assertEqual(TrailEffort.objects.filter(trail__direction='descent').count(), 2)
