"""The top of the Progress screen: rider level, streak, recent points, challenges and the next milestone."""
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from . import content, xp
from .models import Challenge, ChallengeEntry, Reason, XPEntry
from .serializers import XPEntrySerializer
from .services import challenge_goal, challenge_progress, is_open
from .state import next_up, rider_skills

RECENT_XP = 5


def next_milestone(level, next_feature=None):
    """One line toward the next level, naming a feature from next up when there is one."""
    if level['to_next'] is None:
        return 'Top level. Keep cleaning new lines and stacking PRs.'
    target = f"{level['to_next']:,} points to level {level['level'] + 1}"
    if level['next_title'] != level['title']:
        target += f" ({level['next_title']})"
    if next_feature:
        worth = content.rules()['xp']['first_clean_per_grade'] * next_feature.grade
        return f"{target}. A first clean of {next_feature.name} is worth {worth:,}, when you're ready."
    return f'{target}.'


def goal_text(challenge, goal):
    """The goal in plain words: "Clean 3 features you haven't cleaned before"."""
    from trails.models import FeatureType

    if challenge.goal_type == 'next_features':
        return f"Clean {goal} feature{'s' if goal != 1 else ''} you haven't cleaned before"
    if challenge.goal_type == 'features':
        kind = FeatureType(challenge.feature_type).label.lower() if challenge.feature_type else 'feature'
        if challenge.grade_min and challenge.grade_min == challenge.grade_max:
            grades = f'grade {challenge.grade_min} '
        elif challenge.grade_min or challenge.grade_max:
            grades = f"grade {challenge.grade_min or 1}-{challenge.grade_max or 10} "
        else:
            grades = ''
        where = f' at {challenge.system.name}' if challenge.system_id else ''
        return f"Clean every {grades}{kind}{where} ({goal})"
    by_id = content.skills_by_id()
    skills = ' or '.join(by_id[s]['name'] for s in challenge.skill_ids if s in by_id)
    if challenge.goal_type == 'sessions':
        return f"Log {goal} {skills} session{'s' if goal != 1 else ''}"
    return f'Master {skills}'


# Upcoming challenges show this many days before they start.
UPCOMING_DAYS = 45


def next_feature(user):
    from trails.ladders import next_up as feature_next_up  # trails imports progression; import late

    suggestions = feature_next_up(user, limit=1)
    return suggestions[0]['feature'] if suggestions else None


def challenge_data(challenge, entry, today):
    by_id = content.skills_by_id()
    goal = challenge_goal(challenge)
    return {
        'id': challenge.id, 'slug': challenge.slug, 'title': challenge.title, 'description': challenge.description,
        'skills': [{'id': s, 'name': by_id[s]['name']} for s in challenge.skill_ids if s in by_id],
        'goal_type': challenge.goal_type, 'goal_count': goal, 'goal_text': goal_text(challenge, goal),
        'starts_on': challenge.starts_on, 'ends_on': challenge.ends_on,
        'days_left': max(0, (challenge.ends_on - today).days + 1),
        'open': is_open(challenge, today),
        'upcoming': challenge.starts_on > today,
        'joined': entry is not None,
        'progress': min(challenge_progress(entry), goal) if entry else 0,
        'completed_at': entry.completed_at if entry else None,
        'xp': content.rules()['xp']['challenge_complete'],
    }


def challenge_list(user, today=None):
    """Open challenges, plus ones the rider joined that are still running or that they finished."""
    today = today or timezone.localdate()
    entries = {e.challenge_id: e for e in ChallengeEntry.objects.filter(user=user)}
    challenges = [
        c for c in Challenge.objects.select_related('system')
        if is_open(c, today) or (c.id in entries and entries[c.id].completed_at)
        or today < c.starts_on <= today + timedelta(days=UPCOMING_DAYS)
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
        'challenges': [c for c in challenge_list(user, today) if c['joined'] or c['open'] or c['upcoming']],
        'next_milestone': next_milestone(level, next_feature(user)),
    }
