"""The top of the Progress screen: rider level, streak, recent XP, skills and challenges."""
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from . import content, xp
from .models import Challenge, ChallengeEntry, Reason, XPEntry
from .serializers import XPEntrySerializer
from .services import challenge_progress, is_open
from .state import next_up, rider_skills

RECENT_XP = 5


def next_milestone(level, next_skill):
    if level['to_next'] is None:
        return "Top level. Keep mastering skills and stacking PRs."
    target = f"{level['to_next']:,} XP to level {level['level'] + 1}"
    if level['next_title'] != level['title']:
        target += f" ({level['next_title']})"
    if next_skill:
        return f"{target}. Mastering {next_skill['name']} is worth {next_skill['xp']:,}."
    return f'{target}.'


def challenge_data(challenge, entry, today):
    by_id = content.skills_by_id()
    return {
        'id': challenge.id, 'slug': challenge.slug, 'title': challenge.title, 'description': challenge.description,
        'skills': [{'id': s, 'name': by_id[s]['name']} for s in challenge.skill_ids if s in by_id],
        'goal_type': challenge.goal_type, 'goal_count': challenge.goal_count,
        'starts_on': challenge.starts_on, 'ends_on': challenge.ends_on,
        'days_left': max(0, (challenge.ends_on - today).days + 1),
        'open': is_open(challenge, today),
        'joined': entry is not None,
        'progress': min(challenge_progress(entry), challenge.goal_count) if entry else 0,
        'completed_at': entry.completed_at if entry else None,
        'xp': content.rules()['xp']['challenge_complete'],
    }


def challenge_list(user, today=None):
    """Open challenges, plus ones the rider joined that are still running or that they finished."""
    today = today or timezone.localdate()
    entries = {e.challenge_id: e for e in ChallengeEntry.objects.filter(user=user)}
    challenges = [
        c for c in Challenge.objects.all()
        if is_open(c, today) or (c.id in entries and entries[c.id].completed_at)
    ]
    return [challenge_data(c, entries.get(c.id), today) for c in challenges]


def dashboard(user, today=None):
    today = today or timezone.localdate()
    skills = content.skill_tree()['skills']
    by_id = {s['id']: s for s in skills}
    states = rider_skills(user, skills)
    level = xp.level(user)
    level['gain_30d'] = level['total'] - xp.total_xp(user, until=timezone.now() - timedelta(days=30))
    by_reason = dict(
        XPEntry.objects.filter(user=user).values('reason').annotate(t=Sum('amount')).values_list('reason', 't')
    )
    labels = dict(Reason.choices)
    per_tier = content.rules()['xp']['mastery_per_tier']
    upcoming = [
        {'id': sid, 'name': by_id[sid]['name'], 'tier': by_id[sid]['tier'], 'branch': by_id[sid]['branch'],
         'state': states[sid]['state'], 'missing': states[sid]['missing'], 'xp': per_tier * by_id[sid]['tier']}
        for sid in next_up(skills, states)
    ]
    return {
        'level': level,
        'xp_by_reason': [{'reason': r, 'label': labels.get(r, r), 'xp': t} for r, t in by_reason.items() if t],
        'practice_streak_weeks': xp.practice_streak(user, today),
        'recent_xp': XPEntrySerializer(XPEntry.objects.filter(user=user).order_by('-id')[:RECENT_XP], many=True).data,
        'skills': {
            'mastered': sum(1 for v in states.values() if v['state'] == 'mastered'),
            'in_progress': sum(1 for v in states.values() if v['state'] == 'in_progress'),
            'total': len(skills),
            'next_up': upcoming,
        },
        'challenges': [c for c in challenge_list(user, today) if c['joined'] or c['open']],
        'next_milestone': next_milestone(level, upcoming[0] if upcoming else None),
    }
