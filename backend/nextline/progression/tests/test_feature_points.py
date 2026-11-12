from datetime import date, timedelta

from django.test import TestCase

from progression import feature_points, xp
from progression.models import Reason, XPEntry
from trails.models import Feature, FeatureLog, Trail, TrailSystem

from .helpers import make_user

MONDAY = date(2026, 11, 2)


class FeaturePointsTests(TestCase):
    def setUp(self):
        self.rider = make_user()
        self.system = TrailSystem.objects.create(name='Ridge Park', slug='ridge')
        self.trail = self.make_trail('Upper Ridge')

    def make_trail(self, name):
        return Trail.objects.create(name=name, system=self.system, start_lat=0, start_lng=0, end_lat=0, end_lng=0,
                                    length_m=1)

    def feature(self, grade=3, type='drop', trail=None, status='certified'):
        trail = trail or self.trail
        return Feature.objects.create(trail=trail, name=f'{type} {grade}', type=type, grade=grade, lat=0, lng=0,
                                      status=status)

    def log(self, feature, outcome='cleaned', day=MONDAY):
        entry = FeatureLog.objects.create(user=self.rider, feature=feature, outcome=outcome, ridden_on=day,
                                          grade_at_log=feature.grade)
        return entry, feature_points.award_log(entry)

    def amounts(self, awards):
        return [(a.reason, a.amount) for a in awards]

    def test_first_clean_is_20_per_grade(self):
        _, awards = self.log(self.feature(grade=4))
        self.assertEqual(self.amounts(awards), [(Reason.FIRST_CLEAN, 80)])

    def test_repeat_cleans_capped_per_feature_per_week(self):
        drop = self.feature()
        self.log(drop)
        paid = [self.amounts(self.log(drop)[1]) for _ in range(4)]
        self.assertEqual(paid, [[(Reason.REPEAT_CLEAN, 5)]] * 3 + [[]])
        # Another feature has its own cap, and next week the cap resets.
        other = self.feature(grade=2, type='jump')
        self.log(other)
        self.assertEqual(self.amounts(self.log(other)[1]), [(Reason.REPEAT_CLEAN, 5)])
        self.assertEqual(self.amounts(self.log(drop, day=MONDAY + timedelta(days=7))[1]), [(Reason.REPEAT_CLEAN, 5)])

    def test_sketchy_pays_once_and_walked_pays_nothing(self):
        drop = self.feature(grade=6)
        self.assertEqual(self.amounts(self.log(drop, 'sketchy')[1]), [(Reason.SKETCHY, 30)])
        self.assertEqual(self.log(drop, 'sketchy')[1], [])
        walked, awards = self.log(self.feature(grade=2, type='jump'), 'walked')
        self.assertEqual(awards, [])
        self.assertTrue(FeatureLog.objects.filter(pk=walked.pk).exists())  # still logged

    def test_sketchy_then_clean_pays_both(self):
        drop = self.feature(grade=3)
        self.log(drop, 'sketchy')
        self.log(drop)
        self.assertEqual(xp.total_xp(self.rider), 15 + 60)

    def test_award_is_idempotent(self):
        entry, _ = self.log(self.feature())
        self.assertEqual(feature_points.award_log(entry), [])
        self.assertEqual(xp.total_xp(self.rider), 60)

    def test_grade_at_log_is_kept_after_regrading(self):
        drop = self.feature(grade=3)
        self.log(drop)
        Feature.objects.filter(pk=drop.pk).update(grade=7)
        self.assertEqual(xp.total_xp(self.rider), 60)

    def test_drafts_pay_once_certified(self):
        draft = self.feature(grade=5, status='draft')
        self.assertEqual(self.log(draft)[1], [])
        draft.status = 'certified'
        draft.save()
        self.assertEqual(self.amounts(feature_points.catch_up(self.rider)), [(Reason.FIRST_CLEAN, 100)])
        self.assertEqual(feature_points.catch_up(self.rider), [])

    def test_pre_grade_first_cleans_are_not_paid_twice(self):
        drop = self.feature(grade=3)
        xp.award(self.rider, Reason.FEATURE, f'feature:{drop.id}', 20)  # paid under the old rules
        self.assertEqual(self.amounts(self.log(drop)[1]), [(Reason.REPEAT_CLEAN, 5)])

    def test_ledger_total_is_the_sum_of_entries(self):
        drop, jump = self.feature(grade=3), self.feature(grade=2, type='jump')
        self.log(drop)
        self.log(drop)
        self.log(jump, 'sketchy')
        total = sum(XPEntry.objects.filter(user=self.rider).values_list('amount', flat=True))
        self.assertEqual(total, 60 + 5 + 10)
        self.assertEqual(xp.total_xp(self.rider), total)
        entry = XPEntry.objects.filter(user=self.rider).first()
        with self.assertRaises(TypeError):
            entry.amount = 1000
            entry.save()
        with self.assertRaises(TypeError):
            XPEntry.objects.filter(user=self.rider).delete()

    def test_deleting_a_log_adds_corrections(self):
        drop = self.feature(grade=3)
        first, _ = self.log(drop)
        second, _ = self.log(drop)
        self.assertEqual(xp.total_xp(self.rider), 65)
        feature_points.delete_log(second)
        self.assertEqual(xp.total_xp(self.rider), 60)
        self.assertTrue(XPEntry.objects.filter(user=self.rider, reason=Reason.CORRECTION, amount=-5).exists())
        feature_points.delete_log(first)
        self.assertEqual(xp.total_xp(self.rider), 0)
        # Logging it again pays the first clean again.
        self.assertEqual(self.amounts(self.log(drop)[1]), [(Reason.FIRST_CLEAN, 60)])

    def test_deleting_the_first_clean_promotes_the_next(self):
        drop = self.feature(grade=3)
        first, _ = self.log(drop)
        self.log(drop, day=MONDAY + timedelta(days=1))
        feature_points.delete_log(first)
        self.assertEqual(xp.total_xp(self.rider), 60)  # the remaining clean is now the first, not a repeat

    def test_trail_bonus_once_with_enough_features(self):
        features = [self.feature(grade=g, type=t) for g, t in ((1, 'drop'), (2, 'jump'), (3, 'corner'))]
        self.feature(grade=4, status='draft')  # drafts don't count toward completing a trail
        self.log(features[0])
        self.log(features[1])
        _, awards = self.log(features[2])
        self.assertIn((Reason.TRAIL_COMPLETE, 100), self.amounts(awards))
        self.assertNotIn(Reason.TRAIL_COMPLETE, [a.reason for a in self.log(features[2])[1]])

    def test_no_trail_bonus_below_minimum(self):
        a, b = self.feature(grade=1), self.feature(grade=2, type='jump')
        self.log(a)
        self.assertEqual([x.reason for x in self.log(b)[1]], [Reason.FIRST_CLEAN])

    def test_ladder_bonus_across_trails(self):
        lower = self.make_trail('Lower Ridge')
        drops = [self.feature(1), self.feature(2, trail=lower), self.feature(3, trail=lower)]
        for d in drops[:2]:
            self.log(d)
        _, awards = self.log(drops[2])
        self.assertIn((Reason.LADDER_COMPLETE, 150), self.amounts(awards))
