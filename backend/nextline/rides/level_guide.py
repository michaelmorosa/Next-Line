"""Explaining rider level: the XP rules, and specific trail goals worth XP next. What a ride earned is in
progression.ride_xp."""
from django.db.models import Min

from progression import content, xp
from progression.models import Reason
from trails.models import (
    DIFFICULTY_WEIGHT, RIDER_RATED_MAX, Difficulty, Direction, FeatureProgress, FeatureStatus, Trail, trusted_weight,
)
from trails.views import features_with_counts

from . import scoring
from .models import TrailEffort

SUGGESTED_FEATURES = 3
# Air suggestion: how much more airtime to aim for, and the biggest air worth suggesting it below.
AIR_STEP_S = 0.1
AIR_SUGGEST_BELOW_S = 1.0


def feature_xp(trail):
    return round(content.rules()['xp']['feature_cleaned_per_weight'] * trusted_weight(trail.difficulty, trail.owner_id))


def suggestions(user):
    """A few concrete trail goals, most useful first: [{kind, title, detail, xp, trail}]. Skill goals are in the
    dashboard's next-up list."""
    values = content.rules()['xp']
    out = []
    status = dict(FeatureProgress.objects.filter(user=user).values_list('feature_id', 'status'))
    ridden = set(TrailEffort.objects.filter(user=user).values_list('trail_id', flat=True))
    features = [
        f for f in features_with_counts(user).filter(approved=True).select_related('trail')
        if status.get(f.id) != FeatureStatus.CLEANED
    ]

    def rank(f):
        # Ones you've almost got first, then trails you ride, then what others manage, then the most XP.
        return (status.get(f.id) != FeatureStatus.ALMOST, f.trail_id not in ridden, -f.riders_cleaned,
                -feature_xp(f.trail))

    for f in sorted(features, key=rank)[:SUGGESTED_FEATURES]:
        notes = [f'on {f.trail.name}']
        if status.get(f.id) == FeatureStatus.ALMOST:
            notes.append("you've almost got it")
        if f.riders_cleaned:
            notes.append(f"{f.riders_cleaned} rider{'s' if f.riders_cleaned != 1 else ''} cleaned it")
        out.append({'kind': 'feature', 'title': f'Clean {f.name}', 'detail': ' · '.join(notes),
                    'xp': feature_xp(f.trail), 'trail': f.trail_id})

    climbs = (
        TrailEffort.objects.filter(user=user, trail__direction=Direction.CLIMB).values('trail_id', 'trail__name')
        .annotate(fewest=Min('touchdowns')).filter(fewest__gt=0).order_by('fewest').first()
    )
    if climbs:
        trail = Trail.objects.get(pk=climbs['trail_id'])
        out.append({
            'kind': 'climb', 'title': f"Ride {trail.name} without a dab",
            'detail': f"Your best is {climbs['fewest']} foot down",
            'xp': round(values['clean_climb_per_weight'] * trusted_weight(trail.difficulty, trail.owner_id)),
            'trail': trail.id,
        })

    fav = scoring.favorite_trail(user)
    if fav:
        out.append({
            'kind': 'speed', 'title': f"Beat your best on {fav['name']}",
            'detail': 'Every new PR is worth XP', 'xp': values['trail_pr'], 'trail': fav['id'],
        })

    biggest = max(user.rides.values_list('biggest_air_s', flat=True), default=0)
    if 0 < biggest < AIR_SUGGEST_BELOW_S:
        out.append({
            'kind': 'air', 'title': f'Hold {biggest + AIR_STEP_S:.2f} s of air',
            'detail': f'Your biggest is {biggest:.2f} s', 'xp': values['biggest_air'], 'trail': None,
        })
    return out


def level_rules():
    """Everything the "How rider level works" screen explains, straight from progression/content/rules.json."""
    rules = content.rules()
    v, caps, m = rules['xp'], rules['caps'], rules['mastery']
    labels = dict(Difficulty.choices)
    table = xp.thresholds(rules)
    return {
        'version': rules['version'],
        'levels': [{'level': i + 1, 'xp': need, 'title': xp.title_for(i + 1, rules)} for i, need in enumerate(table)],
        'titles': rules['titles'],
        'master_title': rules['master_title'],
        'sources': [
            {'key': Reason.SESSION, 'label': 'Drill sessions',
             'how': f"{v['drill_session']} XP each, up to {caps['drill_sessions_per_skill_per_day']} per skill a day."},
            {'key': Reason.ATTEMPT, 'label': 'Attempt videos',
             'how': f"{v['attempt_video']} XP each, up to {caps['attempt_videos_per_skill_per_day']} per skill a day."},
            {'key': Reason.MASTERY, 'label': 'Skills mastered',
             'how': f"{v['mastery_per_tier']} XP times the skill's tier (1–{max(content.TIERS)}). Needs {m['min_sessions']} sessions on "
                    f"at least {m['min_practice_days']} days and {m['min_videos']} attempt video, then you confirm "
                    "you passed the mastery test."},
            {'key': Reason.STREAK, 'label': 'Practice weeks',
             'how': f"{v['weekly_streak']} XP for each week you practise on "
                    f"{rules['streak']['practice_days_per_week']} or more days."},
            {'key': Reason.CHALLENGE, 'label': 'Challenges', 'how': f"{v['challenge_complete']} XP each."},
            {'key': Reason.FEATURE, 'label': 'Features cleaned',
             'how': f"{v['feature_cleaned_per_weight']} XP times the trail difficulty, the first time. Mark them in "
                    "the check-in."},
            {'key': Reason.PR, 'label': 'Trail PRs', 'how': f"{v['trail_pr']} XP each time you beat your best."},
            {'key': Reason.CLEAN_CLIMB, 'label': 'Clean climbs',
             'how': f"{v['clean_climb_per_weight']} XP times difficulty, the first time you ride a climb with no "
                    "foot down."},
            {'key': Reason.AIR, 'label': 'Biggest air', 'how': f"{v['biggest_air']} XP each new best."},
            {'key': Reason.DESCENT, 'label': 'Descending',
             'how': f"{v['descent_per_100m']} XP per 100 m, up to {caps['descent_xp_per_day']} a day."},
            {'key': Reason.JUMPS, 'label': 'Jumps',
             'how': f"{v['jump']} XP per jump, up to {caps['jump_xp_per_day']} a day."},
            {'key': Reason.RIDE, 'label': 'Rides', 'how': f"{v['ride']} XP for each ride."},
        ],
        'difficulty_weights': [
            {'difficulty': d, 'label': labels[d], 'weight': DIFFICULTY_WEIGHT[d]}
            for d in (Difficulty.GREEN, Difficulty.BLUE, Difficulty.BLACK, Difficulty.DOUBLE_BLACK)
        ],
        'rider_rated_max': labels[RIDER_RATED_MAX],
    }
