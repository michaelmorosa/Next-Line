from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from progression import content, services, xp
from progression.models import Challenge, ChallengeEntry, Mastery, PracticeSession, Reason, XPEntry
from progression.services import ProgressionError
from progression.state import (
    IN_PROGRESS, LOCKED, MASTERED, READY, missing_for_mastery, newly_ready, next_up, rider_skills, skill_state,
)

from .helpers import FOUNDATIONS, TODAY, TempMediaMixin, attempt, make_eligible, make_user, master, practise

SMALL_DROPS = {'id': 'small_drops', 'prerequisites': ['roll_offs', 'manual']}


class SkillStateTests(SimpleTestCase):
    def test_no_prerequisites_is_ready(self):
        self.assertEqual(skill_state({'id': 'a', 'prerequisites': []}, set(), set()), READY)

    def test_multiple_prerequisites_need_all_of_them(self):
        self.assertEqual(skill_state(SMALL_DROPS, set(), set()), LOCKED)
        self.assertEqual(skill_state(SMALL_DROPS, {'roll_offs'}, set()), LOCKED)
        self.assertEqual(skill_state(SMALL_DROPS, {'manual'}, set()), LOCKED)
        self.assertEqual(skill_state(SMALL_DROPS, {'roll_offs', 'manual'}, set()), READY)

    def test_practice_makes_in_progress_and_mastery_wins(self):
        self.assertEqual(skill_state(SMALL_DROPS, {'roll_offs', 'manual'}, {'small_drops'}), IN_PROGRESS)
        self.assertEqual(skill_state(SMALL_DROPS, {'small_drops'}, {'small_drops'}), MASTERED)

    def test_newly_ready_only_when_last_prerequisite_lands(self):
        skills = [{'id': 'roll_offs', 'prerequisites': []}, {'id': 'manual', 'prerequisites': []}, SMALL_DROPS]
        self.assertEqual(newly_ready(skills, set(), {'roll_offs'}), [])
        self.assertEqual(newly_ready(skills, {'roll_offs'}, {'roll_offs', 'manual'}), ['small_drops'])

    def test_missing_for_mastery(self):
        rules = {'mastery': {'min_sessions': 3, 'min_practice_days': 2, 'min_videos': 1}}
        self.assertEqual(missing_for_mastery(1, 1, 0, rules),
                         ['2 more sessions', '1 more practice day', '1 more attempt video'])
        self.assertEqual(missing_for_mastery(3, 2, 1, rules), [])


class LevelTests(SimpleTestCase):
    rules = {'levels': {'first_step': 100, 'growth': 1.2, 'count': 5},
             'titles': [{'from_level': 1, 'title': 'PQ Punk'}, {'from_level': 3, 'title': 'Gravel Grom'}]}

    def test_thresholds_grow_by_twenty_percent(self):
        self.assertEqual(xp.thresholds(self.rules), [0, 100, 220, 364, 537])

    def test_level_boundaries(self):
        self.assertEqual(xp.level_for(0, self.rules)['level'], 1)
        self.assertEqual(xp.level_for(99, self.rules)['level'], 1)
        self.assertEqual(xp.level_for(100, self.rules)['level'], 2)
        self.assertEqual(xp.level_for(219, self.rules)['level'], 2)
        self.assertEqual(xp.level_for(220, self.rules)['level'], 3)

    def test_progress_bar_and_titles(self):
        lv = xp.level_for(160, self.rules)
        self.assertEqual((lv['into_level'], lv['to_next'], lv['fraction']), (60, 60, 0.5))
        self.assertEqual((lv['title'], lv['next_title']), ('PQ Punk', 'Gravel Grom'))
        self.assertEqual(xp.level_for(230, self.rules)['title'], 'Gravel Grom')

    def test_top_level(self):
        lv = xp.level_for(160, {**self.rules, 'master_title': 'MTB Master'}, master=True)
        self.assertEqual((lv['level'], lv['title'], lv['master']), (2, 'MTB Master', True))
        lv = xp.level_for(10_000, self.rules)
        self.assertEqual((lv['level'], lv['to_next'], lv['fraction'], lv['next_at']), (5, None, 1.0, None))

    def test_real_rules(self):
        table = xp.thresholds()
        self.assertEqual(len(table), 20)
        self.assertEqual(table[:3], [0, 100, 222])
        self.assertEqual(xp.title_for(1), 'PQ Punk')
        self.assertEqual(xp.title_for(20), 'Line Legend')


class StreakTests(SimpleTestCase):
    def test_qualifying_weeks_need_three_distinct_days(self):
        monday = TODAY - timedelta(days=TODAY.weekday())
        two_days = {monday, monday + timedelta(days=1)}
        self.assertEqual(xp.qualifying_weeks(two_days, 3), set())
        self.assertEqual(xp.qualifying_weeks(two_days | {monday + timedelta(days=4)}, 3), {monday})


class LedgerTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_total_is_sum_of_entries_including_corrections(self):
        xp.award(self.user, Reason.RIDE, 'ride:1', 2)
        xp.award(self.user, Reason.MASTERY, 'mastery:x', 100)
        xp.award(self.user, Reason.CORRECTION, 'correction:1', -30)
        self.assertEqual(xp.total_xp(self.user), 72)
        self.assertEqual(xp.total_xp(make_user('other')), 0)

    def test_same_source_pays_once(self):
        self.assertIsNotNone(xp.award(self.user, Reason.RIDE, 'ride:1', 2))
        self.assertIsNone(xp.award(self.user, Reason.RIDE, 'ride:1', 2))
        self.assertEqual(xp.total_xp(self.user), 2)

    def test_zero_amount_writes_nothing(self):
        self.assertIsNone(xp.award(self.user, Reason.RIDE, 'ride:1', 0))
        self.assertFalse(XPEntry.objects.exists())

    def test_ledger_is_append_only(self):
        entry = xp.award(self.user, Reason.RIDE, 'ride:1', 2)
        entry.amount = 500
        with self.assertRaises(TypeError):
            entry.save()
        with self.assertRaises(TypeError):
            entry.delete()
        with self.assertRaises(TypeError):
            XPEntry.objects.filter(user=self.user).update(amount=500)
        with self.assertRaises(TypeError):
            XPEntry.objects.filter(user=self.user).delete()
        self.assertEqual(xp.total_xp(self.user), 2)

    def test_entries_record_rules_version(self):
        self.assertEqual(xp.award(self.user, Reason.RIDE, 'ride:1', 2).rules_version, content.rules()['version'])


class PracticeTests(TempMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user()

    def test_new_rider_has_foundations_ready_and_rest_locked(self):
        states = rider_skills(self.user)
        self.assertEqual({s for s, v in states.items() if v['state'] == READY}, set(FOUNDATIONS))
        self.assertEqual(sum(v['state'] == LOCKED for v in states.values()), 47)

    def test_session_earns_xp_and_starts_skill(self):
        result = practise(self.user, 'attack_position')
        self.assertEqual([a.amount for a in result['awards']], [10])
        self.assertEqual(rider_skills(self.user)['attack_position']['state'], IN_PROGRESS)

    def test_daily_cap_per_skill(self):
        for _ in range(3):
            self.assertFalse(practise(self.user, 'attack_position')['capped'])
        fourth = practise(self.user, 'attack_position')
        self.assertTrue(fourth['capped'])
        self.assertEqual(xp.total_xp(self.user), 30)
        # The capped session still counts toward mastery.
        self.assertEqual(rider_skills(self.user)['attack_position']['sessions'], 4)
        # The cap is per skill and per day.
        practise(self.user, 'braking_control')
        practise(self.user, 'attack_position', TODAY + timedelta(days=1))
        self.assertEqual(xp.total_xp(self.user), 50)

    def test_attempt_video_cap(self):
        self.assertEqual([a.amount for a in attempt(self.user, 'attack_position')['awards']], [15])
        self.assertTrue(attempt(self.user, 'attack_position')['capped'])
        self.assertEqual(xp.total_xp(self.user), 15)

    def test_retry_with_same_client_id_is_ignored(self):
        first = practise(self.user, 'attack_position')
        again = services.log_session(self.user, 'attack_position', TODAY, client_id=first['session'].client_id,
                                     today=TODAY)
        self.assertFalse(again['created'])
        self.assertEqual(xp.total_xp(self.user), 10)

    def test_locked_skill_cannot_be_practised(self):
        with self.assertRaisesMessage(ProgressionError, 'Manual is locked'):
            practise(self.user, 'manual')

    def test_bad_drill_and_date(self):
        with self.assertRaises(ProgressionError):
            practise(self.user, 'attack_position', drill_index=9)
        with self.assertRaises(ProgressionError):
            services.log_session(self.user, 'attack_position', TODAY - timedelta(days=5), today=TODAY)

    def test_weekly_streak_awarded_once_on_third_day(self):
        monday = TODAY - timedelta(days=TODAY.weekday())
        practise(self.user, 'attack_position', monday)
        practise(self.user, 'attack_position', monday + timedelta(days=1))
        self.assertFalse(XPEntry.objects.filter(reason=Reason.STREAK).exists())
        third = practise(self.user, 'braking_control', monday + timedelta(days=2))
        self.assertIn(25, [a.amount for a in third['awards']])
        practise(self.user, 'looking_ahead', monday + timedelta(days=3))
        self.assertEqual(XPEntry.objects.filter(reason=Reason.STREAK).count(), 1)

    def test_streak_counts_consecutive_weeks(self):
        monday = TODAY - timedelta(days=TODAY.weekday())
        for weeks_back in (0, 1, 3):  # week 2 back is missing
            for d in range(3):
                practise(self.user, 'attack_position', monday - timedelta(weeks=weeks_back) + timedelta(days=d))
        self.assertEqual(xp.practice_streak(self.user, today=monday + timedelta(days=2)), 2)
        # Early in a week that doesn't count yet, the streak runs from last week.
        self.assertEqual(xp.practice_streak(self.user, today=monday + timedelta(days=7)), 2)
        self.assertEqual(xp.practice_streak(self.user, today=monday + timedelta(days=14)), 0)


class MasteryTests(TempMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user()

    def test_requirements_before_mastery(self):
        practise(self.user, 'attack_position')
        with self.assertRaisesMessage(ProgressionError, '2 more sessions'):
            services.master_skill(self.user, 'attack_position', True)
        # Three sessions on one day isn't enough: it needs two practice days.
        practise(self.user, 'attack_position')
        practise(self.user, 'attack_position')
        attempt(self.user, 'attack_position')
        with self.assertRaisesMessage(ProgressionError, '1 more practice day'):
            services.master_skill(self.user, 'attack_position', True)

    def test_needs_confirmation(self):
        make_eligible(self.user, 'attack_position')
        with self.assertRaisesMessage(ProgressionError, 'Confirm'):
            services.master_skill(self.user, 'attack_position', False)

    def test_mastery_xp_scales_with_tier(self):
        result = master(self.user, 'attack_position')
        self.assertEqual([a.amount for a in result['awards']], [100])
        self.assertEqual(rider_skills(self.user)['attack_position']['state'], MASTERED)
        with self.assertRaises(ProgressionError):
            services.master_skill(self.user, 'attack_position', True)

    def test_unlocks_including_multiple_prerequisites(self):
        unlocked = {}
        for skill in ('attack_position', 'braking_control', 'looking_ahead', 'roll_offs', 'wheel_lift', 'pumping'):
            unlocked[skill] = master(self.user, skill)['unlocked']
        self.assertEqual(unlocked['attack_position'], ['climbing_position', 'wheel_lift', 'pumping'])
        self.assertIn('roll_offs', unlocked['braking_control'])
        self.assertIn('flat_corners', unlocked['looking_ahead'])
        self.assertNotIn('small_drops', unlocked['roll_offs'])  # Manual isn't mastered yet
        self.assertEqual(rider_skills(self.user)['small_drops']['state'], LOCKED)
        manual = master(self.user, 'manual')
        self.assertIn('small_drops', manual['unlocked'])
        self.assertEqual(manual['awards'][0].amount, 300)  # tier 3
        self.assertEqual(rider_skills(self.user)['small_drops']['state'], READY)

    def test_level_before_and_after(self):
        result = master(self.user, 'attack_position')
        self.assertEqual(result['level_before']['total'], 45)  # 3 sessions + 1 attempt
        self.assertEqual(result['level_after']['total'], 145)
        self.assertEqual(result['level_after']['level'], 2)

    def test_mastering_the_capstone_makes_a_master(self):
        capstone = content.capstone_id()
        for skill_id in content.skills_by_id():
            if skill_id != capstone:
                Mastery.objects.create(user=self.user, skill_id=skill_id, confirmed_test=True)
        self.assertFalse(xp.level(self.user)['master'])
        result = master(self.user, capstone)
        self.assertEqual(result['awards'][0].amount, 600)  # tier 6
        self.assertEqual(result['level_after']['title'], content.rules()['master_title'])
        self.assertTrue(xp.level(self.user)['master'])

    def test_coach_verified_is_optional(self):
        master(self.user, 'attack_position')
        self.assertFalse(Mastery.objects.get().coach_verified)
        Mastery.objects.update(coach_verified=True)
        self.assertTrue(rider_skills(self.user)['attack_position']['coach_verified'])

    def test_next_up(self):
        skills = content.skill_tree()['skills']
        self.assertEqual(set(next_up(skills, rider_skills(self.user))), set(FOUNDATIONS))
        practise(self.user, 'looking_ahead')
        self.assertEqual(next_up(skills, rider_skills(self.user))[0], 'looking_ahead')


class ChallengeTests(TempMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.today = timezone.localdate()

    def test_seed_and_complete_sessions_challenge(self):
        challenge = services.seed_challenges(self.today)[0]
        self.assertEqual((challenge.slug, challenge.goal_count), ('30-day-manual', 10))
        self.assertEqual(challenge.ends_on - challenge.starts_on, timedelta(days=29))
        for skill in ('attack_position', 'pumping', 'wheel_lift'):
            master(self.user, skill, self.today)
        before = practise(self.user, 'manual', self.today)['session']  # before joining: doesn't count
        # Clock resolution on some systems can give the session and the join the same timestamp.
        PracticeSession.objects.filter(id=before.id).update(logged_at=timezone.now() - timedelta(minutes=1))
        entry = services.join_challenge(self.user, challenge, self.today)
        self.assertEqual(services.challenge_progress(entry), 0)
        for i in range(9):
            practise(self.user, 'manual', self.today)
        self.assertEqual(services.challenge_progress(entry), 9)
        last = practise(self.user, 'manual', self.today)
        self.assertEqual(len(last['challenges']), 1)
        self.assertEqual(XPEntry.objects.get(reason=Reason.CHALLENGE).amount, 50)
        practise(self.user, 'manual', self.today)
        self.assertEqual(XPEntry.objects.filter(reason=Reason.CHALLENGE).count(), 1)

    def test_master_goal(self):
        challenge = Challenge.objects.create(
            slug='m', title='Master it', skill_ids=['attack_position'], goal_type='master', goal_count=1,
            starts_on=self.today, ends_on=self.today + timedelta(days=5),
        )
        services.join_challenge(self.user, challenge, self.today)
        result = master(self.user, 'attack_position', self.today)
        self.assertEqual(len(result['challenges']), 1)
        self.assertIsNotNone(ChallengeEntry.objects.get().completed_at)

    def test_cannot_join_closed_challenge(self):
        challenge = Challenge.objects.create(
            slug='old', title='Old', skill_ids=['manual'], goal_type='sessions', goal_count=1,
            starts_on=self.today - timedelta(days=40), ends_on=self.today - timedelta(days=10),
        )
        with self.assertRaises(ProgressionError):
            services.join_challenge(self.user, challenge, self.today)
