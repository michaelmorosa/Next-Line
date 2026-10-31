"""Rider level tiers: points get you close, requirements unlock them.

Levels are meant to take seasons, not weeks. From Intermediate up, every tier also needs skill on harder trails
(features cleaned, trails mastered) and time (active weeks: weeks with at least one ride), so nobody can binge
their way up in a month. Difficulty counts the trusted rating (trails.models.trusted_difficulty), and only approved
features count.
"""
from trails.models import Difficulty

from .achievements import cleaned_feature_counts, mastered_trail_counts
from .models import Ride

DIFFICULTY_NAMES = {Difficulty.BLUE: 'blue', Difficulty.BLACK: 'black-diamond', Difficulty.DOUBLE_BLACK: 'double-black'}

B, K, D = Difficulty.BLUE, Difficulty.BLACK, Difficulty.DOUBLE_BLACK

# (points, name, requirements). Requirements: features=(difficulty or harder, count cleaned),
# mastered=(difficulty or harder, trails mastered), weeks=active weeks.
TIERS = [
    (0, 'Beginner I', {}),
    (500, 'Beginner II', {}),
    (1200, 'Beginner III', {}),
    (2000, 'Intermediate I', {'features': (B, 5), 'weeks': 4}),
    (3000, 'Intermediate II', {'features': (B, 10), 'weeks': 6}),
    (4500, 'Intermediate III', {'features': (B, 15), 'mastered': (B, 1), 'weeks': 10}),
    (6500, 'Advanced I', {'features': (K, 5), 'weeks': 16}),
    (9000, 'Advanced II', {'features': (K, 12), 'mastered': (K, 1), 'weeks': 22}),
    (12000, 'Advanced III', {'features': (K, 20), 'mastered': (K, 3), 'weeks': 30}),
    (16000, 'Expert', {'features': (D, 8), 'mastered': (D, 1), 'weeks': 52}),
]


def active_weeks(user, until=None):
    rides = Ride.objects.filter(user=user)
    if until:
        rides = rides.filter(started_at__lte=until)
    return len({tuple(dt.isocalendar()[:2]) for dt in rides.values_list('started_at', flat=True)})


def requirement_stats(user, until=None):
    """What the rider has toward requirements, as of `until`."""
    return {
        'features': cleaned_feature_counts(user, until),
        'mastered': mastered_trail_counts(user, until),
        'weeks': active_weeks(user, until),
    }


def describe(kind, value):
    """Words for one requirement, e.g. "5 blue (or harder) features cleaned"."""
    if kind == 'weeks':
        return f'{value} active weeks'
    difficulty, needed = value
    harder = '' if difficulty == D else ' (or harder)'
    if kind == 'features':
        return f"{needed} {DIFFICULTY_NAMES[difficulty]}{harder} feature{'s' if needed != 1 else ''} cleaned"
    return f"{needed} {DIFFICULTY_NAMES[difficulty]}{harder} trail{'s' if needed != 1 else ''} mastered"


def requirement_progress(requirements, stats):
    """[{kind, difficulty, label, needed, have, met}] for a tier's requirements."""
    out = []
    for kind in ('features', 'mastered', 'weeks'):
        if kind not in requirements:
            continue
        value = requirements[kind]
        if kind == 'weeks':
            difficulty, needed, have = None, value, stats['weeks']
        else:
            difficulty, needed = value
            have = stats[kind][difficulty.value]
        out.append({
            'kind': kind, 'difficulty': difficulty.value if difficulty else None, 'label': describe(kind, value),
            'needed': needed, 'have': min(have, needed), 'met': have >= needed,
        })
    return out


def tier_index(points, stats):
    """The highest tier the rider has both the points and the requirements for. Tiers unlock in order."""
    index = 0
    for i, (threshold, _, requirements) in enumerate(TIERS):
        if points < threshold or not all(r['met'] for r in requirement_progress(requirements, stats)):
            break
        index = i
    return index
