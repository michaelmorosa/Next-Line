"""Explaining rider level: what a ride earned, the rules, and specific ways to level up next."""
from datetime import timedelta

from django.db.models import Min

from trails.models import (
    DIFFICULTY_WEIGHT, RIDER_RATED_MAX, Difficulty, Direction, FeatureProgress, FeatureStatus, Trail, trusted_weight,
)
from trails.views import features_with_counts

from . import scoring, tiers
from .achievements import at_least
from .models import TrailEffort

SUGGESTED_FEATURES = 3
# Air suggestion: how much more airtime to aim for, and the biggest air worth suggesting it below.
AIR_STEP_S = 0.1
AIR_SUGGEST_BELOW_S = 1.0
# Speed suggestion: points for this much faster on your most-ridden descent.
SPEED_STEP = 0.05


def level_at(user, until):
    points, parts = scoring.level_points(user, until=until)
    tier = tiers.TIERS[tiers.tier_index(points, tiers.requirement_stats(user, until))][1]
    return points, parts, tier


def ride_level_gain(ride):
    """Rider level points this ride added, by source, with the reasons in words."""
    last_t = ride.track[-1][0] if ride.track else 0
    after = ride.started_at + timedelta(seconds=max(ride.elapsed_s, last_t) + 60)
    before = ride.started_at - timedelta(microseconds=1)
    points_after, parts_after, tier_after = level_at(ride.user, after)
    points_before, parts_before, tier_before = level_at(ride.user, before)

    highlights = []
    first_cleaned = FeatureProgress.objects.filter(
        user=ride.user, feature_id__in=ride.cleaned_features, first_cleaned_at=ride.started_at,
        feature__approved=True,
    ).select_related('feature__trail')
    for progress in first_cleaned:
        trail = progress.feature.trail
        points = round(scoring.FEATURE_POINTS * trusted_weight(trail.difficulty, trail.owner_id))
        highlights.append(f'Cleaned {progress.feature.name} for the first time (+{points})')
    for effort in ride.efforts.filter(is_pr=True).select_related('trail'):
        highlights.append(f'New PR on {effort.trail.name}')
    if ride.biggest_air_s and ride.biggest_air_s > scoring.biggest_air_before(ride):
        highlights.append(f'Biggest air yet: {ride.biggest_air_s:.2f} s')
    for effort in ride.efforts.filter(touchdowns=0, trail__direction=Direction.CLIMB).select_related('trail'):
        earlier = TrailEffort.objects.filter(
            user=ride.user, trail=effort.trail, touchdowns=0, started_at__lt=effort.started_at,
        ).exists()
        if not earlier:
            highlights.append(f'First clean climb of {effort.trail.name}')

    return {
        'points': points_after - points_before,
        'parts': {k: parts_after[k] - parts_before[k] for k in parts_after if parts_after[k] != parts_before[k]},
        'tier_before': tier_before,
        'tier_after': tier_after,
        'highlights': highlights,
    }


def feature_points(trail):
    return round(scoring.FEATURE_POINTS * trusted_weight(trail.difficulty, trail.owner_id))


def suggestions(user, level):
    """A few concrete things to do next, most useful first: [{kind, title, detail, points, trail}]."""
    out = []
    unmet = {r['kind']: r for r in level.get('requirements', []) if not r['met']}
    needed = unmet.get('features') or unmet.get('mastered')
    unlocks = at_least(Difficulty(needed['difficulty'])) if needed else set()

    status = dict(FeatureProgress.objects.filter(user=user).values_list('feature_id', 'status'))
    ridden = set(TrailEffort.objects.filter(user=user).values_list('trail_id', flat=True))
    features = [
        f for f in features_with_counts(user).filter(approved=True).select_related('trail')
        if status.get(f.id) != FeatureStatus.CLEANED
    ]

    def counts_toward_tier(f):
        return f.trail.owner_id is None and f.trail.difficulty in unlocks

    def rank(f):
        # Tier requirement first, then ones you've almost got, then trails you ride, then what others manage.
        return (not counts_toward_tier(f), status.get(f.id) != FeatureStatus.ALMOST, f.trail_id not in ridden,
                -f.riders_cleaned, -feature_points(f.trail))

    for f in sorted(features, key=rank)[:SUGGESTED_FEATURES]:
        notes = [f'on {f.trail.name}']
        if status.get(f.id) == FeatureStatus.ALMOST:
            notes.append("you've almost got it")
        if counts_toward_tier(f):
            notes.append(f"counts toward {level['next_tier']}")
        if f.riders_cleaned:
            notes.append(f"{f.riders_cleaned} rider{'s' if f.riders_cleaned != 1 else ''} cleaned it")
        out.append({'kind': 'feature', 'title': f'Clean {f.name}', 'detail': ' · '.join(notes),
                    'points': feature_points(f.trail), 'trail': f.trail_id})

    climbs = (
        TrailEffort.objects.filter(user=user, trail__direction=Direction.CLIMB).values('trail_id', 'trail__name')
        .annotate(fewest=Min('touchdowns')).filter(fewest__gt=0).order_by('fewest').first()
    )
    if climbs:
        trail = Trail.objects.get(pk=climbs['trail_id'])
        out.append({
            'kind': 'climb', 'title': f"Ride {trail.name} without a dab",
            'detail': f"Your best is {climbs['fewest']} foot down",
            'points': round(scoring.CLEAN_CLIMB_POINTS * trusted_weight(trail.difficulty, trail.owner_id)),
            'trail': trail.id,
        })

    fav = scoring.favorite_trail(user)
    if fav:
        trail = Trail.objects.get(pk=fav['id'])
        best = TrailEffort.objects.filter(user=user, trail=trail).order_by('elapsed_s').first()
        gain = scoring.SPEED_POINTS_PER_MS * best.avg_speed * SPEED_STEP * trusted_weight(trail.difficulty, trail.owner_id)
        out.append({
            'kind': 'speed', 'title': f'Beat your best on {trail.name}',
            'detail': f"{round(SPEED_STEP * 100)}% faster than your PR adds points",
            'points': max(1, round(gain)), 'trail': trail.id,
        })

    if 'weeks' in unmet:
        weeks = unmet['weeks']
        left = weeks['needed'] - weeks['have']
        out.append({
            'kind': 'weeks', 'title': f"Ride in {left} more week{'s' if left != 1 else ''}",
            'detail': f"{level['next_tier']} needs {weeks['needed']} active weeks; you have {weeks['have']}",
            'points': 0, 'trail': None,
        })

    biggest = max(user.rides.values_list('biggest_air_s', flat=True), default=0)
    if 0 < biggest < AIR_SUGGEST_BELOW_S:
        out.append({
            'kind': 'air', 'title': f'Hold {biggest + AIR_STEP_S:.2f} s of air',
            'detail': f'Your biggest is {biggest:.2f} s',
            'points': round(scoring.AIR_POINTS_PER_S * AIR_STEP_S), 'trail': None,
        })
    return out


def level_rules():
    """Everything the "How rider level works" screen explains, straight from the scoring constants."""
    labels = dict(Difficulty.choices)
    s = scoring
    return {
        'tiers': [
            {'points': points, 'name': name,
             'requirements': [tiers.describe(kind, value) for kind, value in requirements.items()]}
            for points, name, requirements in tiers.TIERS
        ],
        'difficulty_weights': [
            {'difficulty': d, 'label': labels[d], 'weight': DIFFICULTY_WEIGHT[d]}
            for d in (Difficulty.GREEN, Difficulty.BLUE, Difficulty.BLACK, Difficulty.DOUBLE_BLACK)
        ],
        'rider_rated_max': labels[RIDER_RATED_MAX],
        'sources': [
            {'key': 'features', 'label': 'Features cleaned',
             'how': f'{s.FEATURE_POINTS} points each, times the trail difficulty. Mark them in the check-in.'},
            {'key': 'speed', 'label': 'Descent speed',
             'how': f'{s.SPEED_POINTS_PER_MS} points per m/s of your fastest run on each descent, times difficulty. '
                    f'Your best {s.SPEED_TRAILS_COUNTED} descents count.'},
            {'key': 'air', 'label': 'Air',
             'how': f'{s.AIR_POINTS_PER_S} points per second of your biggest air, plus {s.JUMP_POINTS} per jump '
                    f'(up to {s.JUMP_POINTS_CAP}).'},
            {'key': 'descent', 'label': 'Descending',
             'how': f'1 point per {round(1 / s.DESCENT_POINTS_PER_M)} m descended, up to {s.DESCENT_POINTS_CAP}.'},
            {'key': 'climbing', 'label': 'Climbing',
             'how': f'{s.CLEAN_CLIMB_POINTS} points times difficulty for each climb ridden with no foot down, plus up '
                    f'to {s.CLIMB_RATE_POINTS_CAP} for your best climb rate (at {s.CLIMB_RATE_FOR_CAP} m/hour) and '
                    f'up to {s.NONSTOP_POINTS_CAP} for your longest non-stop climb.'},
        ],
    }
