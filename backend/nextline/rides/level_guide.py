"""Explaining rider level: the XP rules, and specific trail goals worth XP next. What a ride earned is in
progression.ride_xp."""
from django.db.models import Min

from progression import content, xp
from progression.models import Reason
from trails.models import (
    DIFFICULTY_WEIGHT, RIDER_RATED_MAX, Difficulty, Direction, Trail, trusted_weight,
)
from trails import progress as feature_progress
from trails.views import features_with_counts

from . import scoring
from .models import TrailEffort

SUGGESTED_FEATURES = 3
# Air suggestion: how much more airtime to aim for, and the biggest air worth suggesting it below.
AIR_STEP_S = 0.1
AIR_SUGGEST_BELOW_S = 1.0


def feature_xp(feature):
    """Points for a first clean of this feature."""
    return content.rules()['xp']['first_clean_per_grade'] * (feature.grade or 0)


def suggestions(user):
    """A few concrete trail goals, most useful first: [{kind, title, detail, xp, trail}]. Skill goals are in the
    dashboard's next-up list."""
    values = content.rules()['xp']
    out = []
    status = {fid: st.status for fid, st in feature_progress.states(user).items()}
    ridden = set(TrailEffort.objects.filter(user=user).values_list('trail_id', flat=True))
    features = [
        f for f in features_with_counts(user).live().select_related('trail')
        if status.get(f.id) != 'cleaned'
    ]

    def rank(f):
        # Ones you've almost got first, then trails you ride, then what others manage, then the most XP.
        return (status.get(f.id) != 'sketchy', f.trail_id not in ridden, -f.riders_cleaned,
                -feature_xp(f))

    for f in sorted(features, key=rank)[:SUGGESTED_FEATURES]:
        notes = [f'on {f.trail.name}']
        if status.get(f.id) == 'sketchy':
            notes.append("you've almost got it")
        if f.riders_cleaned:
            notes.append(f"{f.riders_cleaned} rider{'s' if f.riders_cleaned != 1 else ''} cleaned it")
        out.append({'kind': 'feature', 'title': f'Clean {f.name}', 'detail': ' · '.join(notes),
                    'xp': feature_xp(f), 'trail': f.trail_id})

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
        'sources': [s for s in [
            {'key': Reason.FIRST_CLEAN, 'label': 'First clean of a feature',
             'how': f"{v['first_clean_per_grade']} points times the feature's grade.", 'value': v['first_clean_per_grade']},
            {'key': Reason.REPEAT_CLEAN, 'label': 'Cleaning it again',
             'how': f"{v['repeat_clean']} points, up to {caps['repeat_cleans_per_feature_per_week']} times per "
                    "feature a week.", 'value': v['repeat_clean']},
            {'key': Reason.SKETCHY, 'label': 'Rode it, sketchy',
             'how': f"{v['sketchy_per_grade']} points times the grade, once per feature. Walking it is logged "
                    "too, and that's fine.", 'value': v['sketchy_per_grade']},
            {'key': Reason.TRAIL_COMPLETE, 'label': 'Every feature on a trail',
             'how': f"{v['trail_complete']} bonus points, once per trail.", 'value': v['trail_complete']},
            {'key': Reason.LADDER_COMPLETE, 'label': 'A whole ladder',
             'how': f"{v['ladder_complete']} bonus points for every feature of one type at a trail system.",
             'value': v['ladder_complete']},
            {'key': Reason.SESSION, 'label': 'Drill sessions',
             'how': f"{v['drill_session']} XP each, up to {caps['drill_sessions_per_skill_per_day']} per skill a day.",
             'value': v['drill_session']},
            {'key': Reason.ATTEMPT, 'label': 'Attempt videos',
             'how': f"{v['attempt_video']} XP each, up to {caps['attempt_videos_per_skill_per_day']} per skill a day.",
             'value': v['attempt_video']},
            {'key': Reason.MASTERY, 'label': 'Skills mastered',
             'how': f"{v['mastery_per_tier']} XP times the skill's tier (1–{max(content.TIERS)}). Needs {m['min_sessions']} sessions on "
                    f"at least {m['min_practice_days']} days and {m['min_videos']} attempt video, then you confirm "
                    "you passed the mastery test.", 'value': v['mastery_per_tier']},
            {'key': Reason.STREAK, 'label': 'Practice weeks',
             'how': f"{v['weekly_streak']} XP for each week you practise on "
                    f"{rules['streak']['practice_days_per_week']} or more days.", 'value': v['weekly_streak']},
            {'key': Reason.CHALLENGE, 'label': 'Challenges', 'how': f"{v['challenge_complete']} points each.",
             'value': v['challenge_complete']},
            {'key': Reason.PR, 'label': 'Trail PRs', 'how': f"{v['trail_pr']} points each time you beat your best.",
             'value': v['trail_pr']},
            {'key': Reason.CLEAN_CLIMB, 'label': 'Clean climbs',
             'how': f"{v['clean_climb_per_weight']} points times difficulty, the first time you ride a climb with no "
                    "foot down.", 'value': v['clean_climb_per_weight']},
            {'key': Reason.AIR, 'label': 'Biggest air', 'how': f"{v['biggest_air']} points each new best.",
             'value': v['biggest_air']},
            {'key': Reason.DESCENT, 'label': 'Descending',
             'how': f"{v['descent_per_100m']} points per 100 m, up to {caps['descent_xp_per_day']} a day.",
             'value': v['descent_per_100m']},
            {'key': Reason.JUMPS, 'label': 'Jumps',
             'how': f"{v['jump']} points per jump, up to {caps['jump_xp_per_day']} a day.", 'value': v['jump']},
            {'key': Reason.RIDE, 'label': 'Rides', 'how': f"{v['ride']} points for each ride.", 'value': v['ride']},
        ] if s.pop('value')],  # sources switched off in rules.json (worth 0) aren't shown
        'difficulty_weights': [
            {'difficulty': d, 'label': labels[d], 'weight': DIFFICULTY_WEIGHT[d]}
            for d in (Difficulty.GREEN, Difficulty.BLUE, Difficulty.BLACK, Difficulty.DOUBLE_BLACK)
        ],
        'rider_rated_max': labels[RIDER_RATED_MAX],
    }
