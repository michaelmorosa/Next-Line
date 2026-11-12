import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from progression import xp

from . import ladders, strengths
from .models import Feature, FeatureLog, Trail, TrailSystem

User = get_user_model()


class RiderTestCase(TestCase):
    def setUp(self):
        self.rider = User.objects.create_user(username='rider', email='rider@example.com', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.rider)
        self.system = TrailSystem.objects.create(name='Ridge Park', slug='ridge')
        self.upper = self.trail('Upper Ridge')
        self.lower = self.trail('Lower Ridge')

    def trail(self, name, system=None):
        return Trail.objects.create(name=name, system=system or self.system, start_lat=0, start_lng=0, end_lat=0,
                                    end_lng=0, length_m=1)

    def feature(self, grade, type='drop', trail=None, status='certified', name=None, position=0, **extra):
        if status == 'certified':
            extra.setdefault('last_verified_at', timezone.now())
        return Feature.objects.create(trail=trail or self.upper, name=name or f'{type} g{grade}', type=type,
                                      grade=grade, lat=0, lng=0, status=status, position=position, **extra)

    def log(self, feature, outcome='cleaned', times=1, days_ago=0):
        for _ in range(times):
            FeatureLog.objects.create(user=self.rider, feature=feature, outcome=outcome, grade_at_log=feature.grade,
                                      ridden_on=timezone.localdate() - timedelta(days=days_ago))

    def suggested(self, system=None):
        return [s['feature'].name for s in ladders.next_up(self.rider, system)]


class LadderTests(RiderTestCase):
    def test_ordered_by_grade_then_trail_then_position(self):
        self.feature(3, name='C upper', trail=self.upper)
        self.feature(1, name='A upper 2', trail=self.upper, position=2)
        self.feature(1, name='A upper 1', trail=self.upper, position=1)
        self.feature(1, name='A lower', trail=self.lower)
        self.feature(2, name='Draft', status='draft')
        self.feature(2, name='Closed', status='closed')
        self.feature(2, name='Rebuilt', status='changed')
        drops = ladders.ladders(self.rider, self.system)[0]
        names = [f['name'] for rung in drops['rungs'] for f in rung['features']]
        self.assertEqual(names, ['A lower', 'A upper 1', 'A upper 2', 'Rebuilt', 'C upper'])
        self.assertEqual([r['grade'] for r in drops['rungs']], [1, 2, 3])

    def test_ladders_show_rider_status(self):
        a, b = self.feature(1), self.feature(2)
        self.log(a, times=2)
        self.log(b, 'sketchy')
        drops = ladders.ladders(self.rider, self.system)[0]
        self.assertEqual((drops['cleaned'], drops['total'], drops['best_grade']), (1, 2, 1))
        self.assertEqual([f['status'] for r in drops['rungs'] for f in r['features']], ['cleaned', 'sketchy'])
        self.assertEqual(drops['rungs'][0]['rider_cleans'], 2)

    def test_one_ladder_per_type(self):
        self.feature(1, 'drop')
        self.feature(1, 'corner')
        types = [ladder['type'] for ladder in self.client.get(f'/api/systems/{self.system.id}/ladders/').data['ladders']]
        self.assertEqual(types, ['drop', 'corner'])


class NextUpTests(RiderTestCase):
    def test_new_rider_starts_at_grade_one(self):
        self.feature(1, name='Roll-down')
        self.feature(2, name='Ledge')
        self.assertEqual(self.suggested(), ['Roll-down'])

    def test_needs_two_cleans_of_the_rung_below(self):
        one = self.feature(1, name='One')
        self.feature(2, name='Two')
        self.log(one)
        self.assertEqual(self.suggested(), [])  # one clean of grade 1 isn't enough yet
        self.log(one)  # repeat cleans of the same feature count
        self.assertEqual(self.suggested(), ['Two'])

    def test_never_more_than_one_grade_up(self):
        one = self.feature(1, name='One')
        self.feature(2, name='Two')
        self.feature(3, name='Three')
        self.log(one, times=5)
        self.assertEqual(self.suggested(), ['Two'])

    def test_never_skips_a_rung_even_with_a_higher_clean_elsewhere(self):
        # The rider cleaned a grade 3 drop at another trail system, but here grade 2 is a rung they haven't done.
        elsewhere = self.feature(3, trail=self.trail('Far away', TrailSystem.objects.create(name='Far', slug='far')))
        self.log(elsewhere, times=2)
        one = self.feature(1, name='One')
        self.feature(2, name='Two')
        self.feature(4, name='Four')
        self.log(one, times=2)
        suggested = self.suggested(self.system)
        self.assertIn('Two', suggested)
        self.assertNotIn('Four', suggested)  # grade 2 here and grade 3 need two cleans each first

    def test_missing_rungs_dont_block(self):
        one = self.feature(1, name='One')
        self.feature(2, name='Two', type='corner')
        self.log(one, times=2)
        two = self.feature(2, name='Two drop')
        self.assertIn('Two drop', self.suggested())
        self.log(two, times=2)
        self.feature(3, name='Three drop')
        self.assertIn('Three drop', self.suggested())

    def test_changed_closed_and_drafts_are_never_suggested(self):
        self.feature(1, name='Rebuilt', status='changed')
        self.feature(1, name='Gone', status='closed')
        self.feature(1, name='Draft', status='draft')
        self.assertEqual(self.suggested(), [])

    def test_advanced_grades_need_the_setting(self):
        rungs = [self.feature(g, name=f'G{g}') for g in range(1, 9)]
        for f in rungs[:7]:
            self.log(f, times=2)
        self.assertNotIn('G8', self.suggested())
        self.rider.advanced_features = True
        self.rider.save()
        self.assertIn('G8', self.suggested())

    def test_three_varied_suggestions_with_reasons(self):
        for type_ in ('drop', 'jump', 'corner', 'roots'):
            self.feature(1, type=type_, name=f'{type_} one')
        self.feature(1, type='drop', name='drop one b')
        result = ladders.next_up(self.rider)
        self.assertEqual(len(result), 3)
        self.assertEqual(len({s['feature'].type for s in result}), 3)
        self.assertTrue(all('first rung' in s['reason'] for s in result))

    def test_step_up_reason_names_what_was_cleaned(self):
        one = self.feature(1, name='Root step')
        self.feature(2, name='Ledge', trail=self.lower)
        self.log(one, times=2)
        reason = ladders.next_up(self.rider)[0]['reason']
        self.assertEqual(reason, "You've cleaned grade 1 drops 2 times (Root step). This is the next rung: a grade 2 "
                                 "drop on Lower Ridge.")

    def test_reasons_never_pressure(self):
        one = self.feature(1, name='One')
        two = self.feature(2, name='Two')
        self.feature(2, name='Two again', trail=self.lower)
        self.log(one, times=2)
        self.log(two, 'sketchy')
        reasons = [s['reason'].lower() for s in ladders.next_up(self.rider)]
        self.assertTrue(any('sketchy last time' in r for r in reasons))
        for r in reasons:
            for phrase in ladders.PRESSURE_PHRASES:
                self.assertNotIn(phrase, r)

    def test_sketchy_features_come_first(self):
        self.feature(1, name='A', type='jump')
        b = self.feature(1, name='B', type='jump')
        self.log(b, 'sketchy')
        self.assertEqual(self.suggested()[0], 'B')

    def test_api(self):
        self.feature(1, name='One')
        data = self.client.get('/api/next-up/').data
        self.assertEqual(data['next_up'][0]['name'], 'One')
        self.assertIn('first rung', data['next_up'][0]['reason'])
        self.assertEqual(data['advanced_above_grade'], 7)


class StrengthTests(RiderTestCase):
    def test_strongest_and_weakest_areas(self):
        drops = [self.feature(g, 'drop', skill_tags=['small_drops']) for g in (2, 3, 4)]
        corners = [self.feature(g, 'corner', skill_tags=['berms']) for g in (2, 3, 4)]
        for d in drops:
            self.log(d)
        self.log(corners[0])
        self.log(corners[1], 'sketchy')
        self.log(corners[2], 'walked')
        summary = strengths.summary(self.rider)
        self.assertEqual(summary['strongest']['name'], 'Drops')
        self.assertEqual(summary['strongest']['score'], 100)
        self.assertEqual(summary['weakest']['name'], 'Cornering')
        # (2 x 1 + 3 x 0.5 + 4 x 0) / (2 + 3 + 4)
        self.assertEqual(summary['weakest']['score'], round(100 * 3.5 / 9))

    def test_untagged_features_use_their_type(self):
        for g in (1, 2, 3):
            self.log(self.feature(g, 'jump'))
        self.assertEqual(strengths.summary(self.rider)['strongest']['name'], 'Air')

    def test_needs_enough_logs(self):
        self.log(self.feature(1, 'drop'))
        self.assertIsNone(strengths.summary(self.rider)['strongest'])


class LoggingApiTests(RiderTestCase):
    def test_one_tap_log(self):
        f = self.feature(3)
        res = self.client.post(f'/api/features/{f.id}/log/', {'outcome': 'cleaned'}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['points'], 60)
        self.assertTrue(res.data['logs'][0]['first_clean'])
        self.assertEqual(res.data['level']['total'], 60)
        self.assertIn('first_feature', [a['key'] for a in res.data['new_achievements']])

    def test_retry_is_safe(self):
        f = self.feature(3)
        body = {'outcome': 'cleaned', 'client_id': str(uuid.uuid4())}
        self.client.post(f'/api/features/{f.id}/log/', body, format='json')
        res = self.client.post(f'/api/features/{f.id}/log/', body, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(FeatureLog.objects.count(), 1)
        self.assertEqual(xp.total_xp(self.rider), 60)

    def test_walked_is_logged_without_points(self):
        f = self.feature(5)
        res = self.client.post(f'/api/features/{f.id}/log/', {'outcome': 'walked', 'note': 'Wet today'},
                               format='json')
        self.assertEqual((res.data['points'], res.data['logs'][0]['note']), (0, 'Wet today'))

    def test_cannot_log_drafts_or_closed(self):
        for status in ('draft', 'closed'):
            f = self.feature(1, status=status)
            self.assertEqual(self.client.post(f'/api/features/{f.id}/log/', {'outcome': 'cleaned'},
                                              format='json').status_code, 404)

    def test_log_this_trail(self):
        a, b, c = self.feature(1, position=1), self.feature(2, 'jump', position=2), self.feature(3, 'corner', position=3)
        res = self.client.post('/api/logs/batch/', {'ridden_on': str(timezone.localdate()), 'logs': [
            {'feature': a.id, 'outcome': 'cleaned'},
            {'feature': b.id, 'outcome': 'sketchy'},
            {'feature': c.id, 'outcome': 'walked'},
        ]}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['points'], 20 + 10 + 0)  # one cleaned, so no trail bonus yet
        self.assertEqual(FeatureLog.objects.count(), 3)

    def test_batch_rejects_features_not_open(self):
        draft = self.feature(1, status='draft')
        res = self.client.post('/api/logs/batch/', {'logs': [{'feature': draft.id, 'outcome': 'cleaned'}]},
                               format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(FeatureLog.objects.count(), 0)

    def test_future_dates_rejected(self):
        f = self.feature(1)
        res = self.client.post(f'/api/features/{f.id}/log/', {
            'outcome': 'cleaned', 'ridden_on': str(timezone.localdate() + timedelta(days=3))}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_delete_own_log_only(self):
        f = self.feature(2)
        log_id = self.client.post(f'/api/features/{f.id}/log/', {'outcome': 'cleaned'}, format='json').data['logs'][0]['id']
        other = APIClient()
        other.force_authenticate(User.objects.create_user(username='o', email='o@example.com', password='x'))
        self.assertEqual(other.delete(f'/api/logs/{log_id}/').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/logs/{log_id}/', {'note': 'Smooth'}, format='json').data['note'],
                         'Smooth')
        self.assertEqual(self.client.delete(f'/api/logs/{log_id}/').status_code, 204)
        self.assertEqual(xp.total_xp(self.rider), 0)


class PagesApiTests(RiderTestCase):
    def test_trail_system_page(self):
        a, b = self.feature(1, position=1), self.feature(2, position=2)
        self.feature(1, trail=self.lower)
        self.log(a)
        data = self.client.get(f'/api/systems/{self.system.id}/').data
        upper = next(t for t in data['trails'] if t['name'] == 'Upper Ridge')
        self.assertEqual((upper['feature_count'], upper['cleaned_count']), (2, 1))
        self.assertEqual((data['feature_count'], data['cleaned_count']), (3, 1))
        self.assertEqual(data['ladders'][0]['type'], 'drop')
        listed = self.client.get('/api/systems/').data[0]
        self.assertEqual((listed['name'], listed['cleaned_count']), ('Ridge Park', 1))

    def test_trail_page_in_riding_order(self):
        self.feature(2, name='Second', position=2)
        self.feature(1, name='First', position=1)
        data = self.client.get(f'/api/trails/{self.upper.id}/features/').data
        self.assertEqual([f['name'] for f in data['features']], ['First', 'Second'])
        self.assertEqual(data['features'][0]['my_status'], 'not_yet')
        self.assertIn('ride-around', data['safety'])

    def test_feature_page(self):
        f = self.feature(4, has_ride_around=True, ride_around_grade=1, ride_around_note='Left of the rock',
                         how_to_ride='Speed, then a manual off the lip.', skill_tags=['small_drops'],
                         drop_height_m=0.9)
        self.log(f, 'sketchy')
        data = self.client.get(f'/api/features/{f.id}/').data
        self.assertTrue(data['has_ride_around'])
        self.assertEqual((data['ride_around_grade'], data['ride_around_note']), (1, 'Left of the rock'))
        self.assertEqual(data['measurements'], {'drop_height_m': 0.9})
        self.assertEqual(data['stuck'][0]['name'], 'Small drops')
        self.assertTrue(data['stuck'][0]['drills'])
        self.assertTrue(data['safety']['needs_legal_review'])
        self.assertEqual([h['outcome'] for h in data['history']], ['sketchy'])
        self.assertEqual(data['notices'], [])
        self.assertEqual(data['first_clean_points'], 80)

    def test_changed_and_stale_notices(self):
        f = self.feature(2, status='changed')
        self.assertIn('changed since we graded it', self.client.get(f'/api/features/{f.id}/').data['notices'][0])
        g = self.feature(2, last_verified_at=timezone.now() - timedelta(days=400))
        data = self.client.get(f'/api/features/{g.id}/').data
        self.assertTrue(data['stale'])
        self.assertIn('Not recently verified', data['notices'][0])

    def test_dashboard(self):
        drops = [self.feature(g, 'drop') for g in (1, 2, 3)]
        for d in drops:
            self.log(d)
        corner = self.feature(1, 'corner')
        self.log(corner)
        data = self.client.get('/api/progress/').data['features']
        self.assertEqual([(t['type'], t['cleaned'], t['best_grade']) for t in data['cleaned_by_type']],
                         [('drop', 3, 3), ('corner', 1, 1)])
        self.assertEqual(data['features_cleaned'], 4)
        self.assertEqual(len(data['recent']), 4)
        self.assertEqual(data['strengths']['strongest']['name'], 'Drops')


class SettingsTests(RiderTestCase):
    def test_advanced_features_setting(self):
        res = self.client.patch('/api/user/me/', {'advanced_features': True}, format='json')
        self.assertTrue(res.data['advanced_features'])
        self.assertFalse(res.data['is_trail_team'])

    def test_accepting_the_safety_notice(self):
        me = self.client.get('/api/user/me/').data
        self.assertEqual((me['safety_version'], me['safety_current_version']), (0, 1))
        self.assertEqual(self.client.patch('/api/user/me/', {'safety_version': 7}, format='json').status_code, 400)
        res = self.client.patch('/api/user/me/', {'safety_version': 1}, format='json')
        self.assertIsNotNone(res.data['safety_accepted_at'])

    def test_signup_needs_the_safety_notice(self):
        client = APIClient()
        body = {'username': 'new', 'email': 'new@example.com', 'password': 'gnarly-line-42',
                're_password': 'gnarly-line-42', 'accepted_safety': False}
        self.assertEqual(client.post('/api/auth/users/', body, format='json').status_code, 400)
        self.assertEqual(client.post('/api/auth/users/', {**body, 'accepted_safety': True},
                                     format='json').status_code, 201)
        user = User.objects.get(username='new')
        self.assertEqual(user.safety_version, 1)
        self.assertIsNotNone(user.safety_accepted_at)

    def test_safety_text(self):
        data = self.client.get('/api/safety/').data
        self.assertTrue(data['needs_legal_review'])
        self.assertIn('responsible', ' '.join(data['full']))
