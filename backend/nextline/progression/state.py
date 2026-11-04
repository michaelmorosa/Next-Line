"""Where a rider is on the tree. Computed from practice, attempt and mastery rows every time, never stored."""
from collections import defaultdict

from django.db.models import Sum

from . import content
from .models import Attempt, Mastery, PracticeSession, XPEntry

LOCKED, READY, IN_PROGRESS, MASTERED = 'locked', 'ready', 'in_progress', 'mastered'
NEXT_UP_COUNT = 3


def skill_state(skill, mastered, practiced):
    """mastered > in progress (any practice logged) > ready (every prerequisite mastered) > locked."""
    if skill['id'] in mastered:
        return MASTERED
    if skill['id'] in practiced:
        return IN_PROGRESS
    if all(p in mastered for p in skill['prerequisites']):
        return READY
    return LOCKED


def missing_for_mastery(sessions, days, videos, rules=None):
    """What's still needed before the rider can confirm the mastery test, e.g. ['1 more session']."""
    m = (rules or content.rules())['mastery']
    out = []
    for have, need, word in ((sessions, m['min_sessions'], 'session'), (days, m['min_practice_days'], 'practice day'),
                             (videos, m['min_videos'], 'attempt video')):
        if have < need:
            n = need - have
            out.append(f"{n} more {word}{'s' if n != 1 else ''}")
    return out


def rider_skills(user, skills=None):
    """Skill id -> {state, sessions, practice_days, attempts, xp, mastered_at, coach_verified, missing, eligible}."""
    skills = skills or content.skill_tree()['skills']
    masteries = {m.skill_id: m for m in Mastery.objects.filter(user=user)}
    sessions = defaultdict(int)
    days = defaultdict(set)
    for skill_id, day in PracticeSession.objects.filter(user=user).values_list('skill_id', 'practiced_on'):
        sessions[skill_id] += 1
        days[skill_id].add(day)
    attempts = defaultdict(int)
    for skill_id in Attempt.objects.filter(user=user).values_list('skill_id', flat=True):
        attempts[skill_id] += 1
    xp = dict(
        XPEntry.objects.filter(user=user).exclude(skill_id='').values('skill_id').annotate(t=Sum('amount'))
        .values_list('skill_id', 't')
    )
    practiced = set(sessions) | set(attempts)
    out = {}
    for skill in skills:
        sid = skill['id']
        mastery = masteries.get(sid)
        state = skill_state(skill, masteries, practiced)
        missing = [] if mastery else missing_for_mastery(sessions[sid], len(days[sid]), attempts[sid])
        out[sid] = {
            'state': state,
            'sessions': sessions[sid],
            'practice_days': len(days[sid]),
            'attempts': attempts[sid],
            'xp': xp.get(sid, 0),
            'mastered_at': mastery.mastered_at if mastery else None,
            'coach_verified': bool(mastery and mastery.coach_verified),
            'missing': missing,
            'eligible': state == IN_PROGRESS and not missing,
        }
    return out


def can_practice(state):
    return state != LOCKED


def next_up(skills, states, count=NEXT_UP_COUNT):
    """1–3 skills to work on: in-progress ones closest to mastery first, then ready ones, easiest tier first. Ties go
    to the skill that unlocks the most."""
    unlocks = content.unlocks(skills)
    in_progress = [s for s in skills if states[s['id']]['state'] == IN_PROGRESS]
    ready = [s for s in skills if states[s['id']]['state'] == READY]
    in_progress.sort(key=lambda s: (len(states[s['id']]['missing']), s['tier'], -len(unlocks[s['id']])))
    ready.sort(key=lambda s: (s['tier'], -len(unlocks[s['id']])))
    return [s['id'] for s in (in_progress + ready)[:count]]


def newly_ready(skills, mastered_before, mastered_now):
    """Skills that became ready because of the latest mastery: all prerequisites mastered now, but not before."""
    return [
        s['id'] for s in skills
        if s['id'] not in mastered_now and s['prerequisites']
        and all(p in mastered_now for p in s['prerequisites'])
        and not all(p in mastered_before for p in s['prerequisites'])
    ]
