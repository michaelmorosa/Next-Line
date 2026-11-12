"""Strengths and weak spots from skill tags. Each log counts toward every skill its feature uses, weighted by the
feature's grade: cleaned 1, sketchy 0.5, walked 0. Skills roll up to their area (Drops, Cornering...).
"""
from collections import defaultdict

from progression import content

from .models import FeatureLog, Outcome
from .skills import branch_names, tags_for

SCORE = {Outcome.CLEANED: 1.0, Outcome.SKETCHY: 0.5, Outcome.WALKED: 0.0}
# An area needs this many logs before it's called a strength or a weak spot.
MIN_LOGS = 3


def skill_scores(user):
    """{skill_id: {'earned', 'possible', 'logs'}}"""
    scores = defaultdict(lambda: {'earned': 0.0, 'possible': 0.0, 'logs': 0})
    for log in FeatureLog.objects.filter(user=user).select_related('feature'):
        weight = log.grade_at_log or log.feature.grade or 1
        for skill_id in tags_for(log.feature):
            s = scores[skill_id]
            s['earned'] += weight * SCORE[log.outcome]
            s['possible'] += weight
            s['logs'] += 1
    return scores


def areas(user):
    """[{area, name, score 0-100, logs, skills}] for areas with at least MIN_LOGS logs, strongest first."""
    skills = content.skills_by_id()
    names = branch_names()
    rolled = defaultdict(lambda: {'earned': 0.0, 'possible': 0.0, 'logs': 0, 'skills': []})
    for skill_id, s in skill_scores(user).items():
        area = skills[skill_id]['branch']
        r = rolled[area]
        r['earned'] += s['earned']
        r['possible'] += s['possible']
        r['logs'] += s['logs']
        r['skills'].append({'skill': skill_id, 'name': skills[skill_id]['name'],
                            'score': round(100 * s['earned'] / s['possible']) if s['possible'] else 0})
    out = [
        {'area': area, 'name': names.get(area, area), 'score': round(100 * r['earned'] / r['possible']),
         'logs': r['logs'], 'skills': sorted(r['skills'], key=lambda s: s['score'])}
        for area, r in rolled.items() if r['logs'] >= MIN_LOGS and r['possible']
    ]
    return sorted(out, key=lambda a: (-a['score'], a['name']))


def summary(user):
    """{'strongest': area or None, 'weakest': area or None, 'areas': [...]}. Weakest is only given when it differs
    from the strongest; it carries the skills to look at first, for "Stuck?" tips."""
    ranked = areas(user)
    strongest = ranked[0] if ranked else None
    weakest = ranked[-1] if len(ranked) > 1 and ranked[-1]['score'] < ranked[0]['score'] else None
    return {'strongest': strongest, 'weakest': weakest, 'areas': ranked}
