"""A demo rider with about six weeks of history, so the progression system can be shown straight away.

Everything goes through the same services the API uses (caps, streaks, unlocks and the ledger behave as they would
live), only backdated. Running it again deletes and recreates the demo rider.
"""
import math
import secrets
import uuid
from datetime import datetime, time, timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from progression import ride_xp, services, xp
from progression.models import Attempt, Challenge
from rides.processing import create_ride

SAMPLE_CLIP = Path(__file__).resolve().parents[2] / 'demo' / 'sample.mp4'
FOUNDATIONS = ('attack_position', 'braking_control', 'looking_ahead')
SECOND_TIER = ('pumping', 'wheel_lift', 'roll_offs')
# Day offsets inside a week (0 = Monday).
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
START = (50.116, -122.957)  # somewhere with good trails


def demo_track(descent_speed, drop=180, climb_s=700):
    """A steady climb north, then a descent east: [t, lat, lng, alt, speed] once a second."""
    m_per_lat = 111195
    m_per_lng = m_per_lat * math.cos(math.radians(START[0]))
    lat, lng, alt, t, points = START[0], START[1], 650.0, 0, []
    for _ in range(climb_s):
        lat += 2.5 / m_per_lat
        alt += drop / climb_s
        t += 1
        points.append([t, lat, lng, alt, 2.5])
    covered = 0.0
    while covered < 1900:
        speed = descent_speed + 0.8 * math.sin(t / 4)
        covered += speed
        lng += speed / m_per_lng
        alt -= drop * speed / 1900
        t += 1
        points.append([t, lat, lng, alt, speed])
    return points


class Command(BaseCommand):
    help = 'Create (or recreate) a demo rider with mastered skills, skills in progress, a streak and rides.'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='demo')
        parser.add_argument('--password', help='Default: a random one, printed at the end')

    def handle(self, *args, **options):
        User = get_user_model()
        today = timezone.localdate()
        this_monday = today - timedelta(days=today.weekday())
        password = options['password'] or secrets.token_urlsafe(9)

        def week(n, day):
            """A date `n` weeks before this week's Monday, on weekday `day`."""
            return this_monday - timedelta(weeks=n) + timedelta(days=day)

        def at(d, hour=17):
            return timezone.make_aware(datetime.combine(d, time(hour, 0)))

        def practise(skill_id, d, drill=0):
            services.log_session(user, skill_id, d, client_id=uuid.uuid4(), drill_index=drill, today=d, at=at(d))

        def film(skill_id, d):
            clip = ContentFile(SAMPLE_CLIP.read_bytes(), name='attempt.mp4')
            services.add_attempt(user, skill_id, clip, d, client_id=uuid.uuid4(), duration_s=4, today=d, at=at(d, 18))

        with transaction.atomic():
            old = User.objects.filter(username=options['username']).first()
            if old:
                for attempt in Attempt.objects.filter(user=old):
                    attempt.video.delete(save=False)
                old.delete()
            user = User.objects.create_user(
                username=options['username'], email=f"{options['username']}@demo.nextline.app", password=password,
            )
            # Starts the challenge two weeks back on a fresh database; an existing one keeps its dates.
            services.seed_challenges(today - timedelta(days=16))

            # Weeks 5–4 back: the foundations, mastered on Sunday of week 4. Every week has 3+ practice days: a streak.
            for d in (week(5, MON), week(5, WED), week(5, SAT), week(4, TUE), week(4, SAT)):
                for i, skill in enumerate(FOUNDATIONS):
                    practise(skill, d, drill=i % 2)
            for skill in FOUNDATIONS:
                film(skill, week(4, THU))
                services.master_skill(user, skill, confirmed_test=True, at=at(week(4, SUN), 19))

            # Weeks 3–2 back: pumping, wheel lift and roll-offs, mastered on Saturday of week 2.
            for d in (week(3, MON), week(3, WED), week(3, FRI), week(2, TUE), week(2, THU), week(2, FRI)):
                for i, skill in enumerate(SECOND_TIER):
                    practise(skill, d, drill=i % 2)
            for skill in SECOND_TIER:
                film(skill, week(2, THU))
                services.master_skill(user, skill, confirmed_test=True, at=at(week(2, SAT), 19))

            # Last week and this week: the manual challenge (6 of 10) and flat corners started.
            challenge, _ = Challenge.objects.update_or_create(slug='demo-manual', defaults={
                'title': '30-day manual challenge', 'skill_ids': ['manual'], 'goal_type': 'sessions', 'goal_count': 10,
                'starts_on': week(2, MON), 'ends_on': week(2, MON) + timedelta(days=29),
            })
            entry = services.join_challenge(user, challenge, today=max(challenge.starts_on, week(1, MON)))
            entry.joined_at = at(max(challenge.starts_on, week(1, MON)), 7)
            entry.save(update_fields=['joined_at'])
            for d in (week(1, MON), week(1, WED), week(1, THU), week(1, FRI), week(1, SAT), this_monday):
                practise('manual', max(d, challenge.starts_on), drill=d.weekday() % 3)
            film('manual', week(1, FRI))
            practise('flat_corners', this_monday)
            practise('flat_corners', this_monday, drill=1)

            # Some rides, getting a little faster.
            for n, (d, speed) in enumerate(((week(5, SUN), 6.0), (week(3, SUN), 6.6), (week(1, SUN), 7.2))):
                ride = create_ride(user, uuid.uuid4(), at(d, 10), 1500, demo_track(speed), [
                    {'t': 760 + 20 * j, 'airtime_s': 0.3 + 0.1 * n + 0.05 * j} for j in range(3 + n)
                ])
                ride_xp.award_ride(ride)

        level = xp.level(user)
        self.stdout.write(self.style.SUCCESS(
            f"Demo rider ready: {user.username} / {password}\n"
            f"Level {level['level']} ({level['title']}), {level['total']:,} XP, "
            f"{xp.practice_streak(user, today)}-week practice streak."
        ))
