"""XP awards, levels and practice streaks. Every value comes from content/rules.json."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from . import content
from .models import Attempt, Mastery, PracticeSession, Reason, XPEntry


def award(user, reason, source, amount, *, skill_id='', challenge=None, at=None):
    """Append one ledger entry, or None if `source` has already paid out or the amount is 0."""
    if not amount:
        return None
    try:
        with transaction.atomic():
            return XPEntry.objects.create(
                user=user, amount=amount, reason=reason, source=source, skill_id=skill_id, challenge=challenge,
                rules_version=content.rules()['version'], created_at=at or timezone.now(),
            )
    except IntegrityError:
        return None


def total_xp(user, until=None):
    entries = XPEntry.objects.filter(user=user)
    if until:
        entries = entries.filter(created_at__lte=until)
    return entries.aggregate(t=Sum('amount'))['t'] or 0


# Levels.

def thresholds(rules=None):
    """Total XP needed for each level: [0, 100, 220, 364, ...]. Level 2 needs `first_step`, and each step after
    that is `growth` times bigger than the one before."""
    levels = (rules or content.rules())['levels']
    out, step, total = [0], levels['first_step'], 0
    for _ in range(levels['count'] - 1):
        total += step
        out.append(round(total))
        step *= levels['growth']
    return out


def title_for(level, rules=None):
    title = None
    for t in (rules or content.rules())['titles']:
        if t['from_level'] <= level:
            title = t['title']
    return title


def level_for(total, rules=None, master=False):
    """Level, title and the progress bar for a total. A rider who has mastered the capstone skill (the whole tree)
    gets the master title whatever their level."""
    rules = rules or content.rules()
    table = thresholds(rules)
    level = max(i + 1 for i, need in enumerate(table) if total >= need) if total >= 0 else 1
    floor = table[level - 1]
    top = level == len(table)
    next_at = None if top else table[level]
    return {
        'level': level,
        'title': rules['master_title'] if master else title_for(level, rules),
        'master': master,
        'total': total,
        'level_floor': floor,
        'next_at': next_at,
        'next_title': None if top else title_for(level + 1, rules),
        'into_level': total - floor,
        'to_next': None if top else next_at - total,
        'fraction': 1.0 if top else round((total - floor) / (next_at - floor), 3),
        'max_level': len(table),
    }


def is_master(user):
    capstone = content.capstone_id()
    return bool(capstone) and Mastery.objects.filter(user=user, skill_id=capstone).exists()


def level(user):
    return level_for(total_xp(user), master=is_master(user))


# Practice days and streaks.

def week_key(day):
    year, week, _ = day.isocalendar()
    return f'{year}-W{week:02d}'


def week_start(day):
    return day - timedelta(days=day.weekday())


def practice_days(user):
    """Every local date the rider logged a session or an attempt."""
    days = set(PracticeSession.objects.filter(user=user).values_list('practiced_on', flat=True))
    days |= set(Attempt.objects.filter(user=user).values_list('practiced_on', flat=True))
    return days


def qualifying_weeks(days, needed=None):
    """Monday of every week with practice on at least `needed` days."""
    needed = needed or content.rules()['streak']['practice_days_per_week']
    per_week = {}
    for day in days:
        per_week.setdefault(week_start(day), set()).add(day)
    return {monday for monday, ds in per_week.items() if len(ds) >= needed}


def practice_streak(user, today=None):
    """Consecutive practice weeks, counting back from this week (or last week, if this one doesn't count yet)."""
    today = today or timezone.localdate()
    weeks = qualifying_weeks(practice_days(user))
    current = week_start(today)
    if current not in weeks:
        current -= timedelta(weeks=1)
    streak = 0
    while current in weeks:
        streak += 1
        current -= timedelta(weeks=1)
    return streak


def award_streak(user, day, at=None):
    """The weekly practice bonus, the first time the week of `day` has enough practice days."""
    monday = week_start(day)
    if monday not in qualifying_weeks({d for d in practice_days(user) if week_start(d) == monday}):
        return None
    return award(user, Reason.STREAK, f'streak:{week_key(day)}', content.rules()['xp']['weekly_streak'], at=at)


# Capped awards.

def nth_today(model, item):
    """1 for the rider's first `model` row on this skill and local date, 2 for the second..."""
    return model.objects.filter(
        user=item.user, skill_id=item.skill_id, practiced_on=item.practiced_on, id__lte=item.id,
    ).count()


def award_session(session):
    rules = content.rules()
    if nth_today(PracticeSession, session) > rules['caps']['drill_sessions_per_skill_per_day']:
        return None
    return award(session.user, Reason.SESSION, f'session:{session.id}', rules['xp']['drill_session'],
                 skill_id=session.skill_id, at=session.logged_at)


def award_attempt(attempt):
    rules = content.rules()
    if nth_today(Attempt, attempt) > rules['caps']['attempt_videos_per_skill_per_day']:
        return None
    return award(attempt.user, Reason.ATTEMPT, f'attempt:{attempt.id}', rules['xp']['attempt_video'],
                 skill_id=attempt.skill_id, at=attempt.created_at)
