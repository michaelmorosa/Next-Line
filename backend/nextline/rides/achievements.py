"""One-off milestones ("achievements"). Earned ones are saved with the date, so they never disappear.

award() is called after anything that can earn one: uploading a ride, a check-in, marking a feature, and opening
Progress (which also backfills riders who earned something before it existed).
"""
from django.db.models import Count, Max, Sum

from trails.models import DIFFICULTY_WEIGHT, Difficulty, Direction, Feature, FeatureProgress, FeatureStatus, trusted_difficulty

from .models import Achievement, Ride, TrailEffort

# A trail needs at least this many features before cleaning them all counts as mastering it.
MASTERY_MIN_FEATURES = 3


def at_least(difficulty):
    """Difficulties as hard as `difficulty` or harder."""
    weight = DIFFICULTY_WEIGHT[difficulty]
    return {d for d, w in DIFFICULTY_WEIGHT.items() if w >= weight and d != Difficulty.UNRATED}


def cleaned_feature_counts(user, until=None):
    """{'any': n, 'blue': n, 'black': n, 'double_black': n}: features cleaned at each trusted difficulty or harder."""
    cleaned = FeatureProgress.objects.filter(user=user, status=FeatureStatus.CLEANED, feature__approved=True)
    if until:
        cleaned = cleaned.filter(first_cleaned_at__lte=until)
    difficulties = [
        trusted_difficulty(d, owner)
        for d, owner in cleaned.values_list('feature__trail__difficulty', 'feature__trail__owner_id')
    ]
    counts = {'any': len(difficulties)}
    for level in (Difficulty.BLUE, Difficulty.BLACK, Difficulty.DOUBLE_BLACK):
        harder = at_least(level)
        counts[level.value] = sum(1 for d in difficulties if d in harder)
    return counts


def mastered_trail_difficulties(user, until=None):
    """Trusted difficulty of each trail this rider has mastered: every approved feature cleaned, with at least
    MASTERY_MIN_FEATURES of them."""
    trails = (
        Feature.objects.filter(approved=True).values('trail_id', 'trail__difficulty', 'trail__owner_id')
        .annotate(total=Count('id')).filter(total__gte=MASTERY_MIN_FEATURES)
    )
    cleaned = FeatureProgress.objects.filter(user=user, status=FeatureStatus.CLEANED, feature__approved=True)
    if until:
        cleaned = cleaned.filter(first_cleaned_at__lte=until)
    counts = dict(cleaned.values('feature__trail_id').annotate(n=Count('id')).values_list('feature__trail_id', 'n'))
    return [
        trusted_difficulty(t['trail__difficulty'], t['trail__owner_id'])
        for t in trails if counts.get(t['trail_id'], 0) >= t['total']
    ]


def mastered_trail_counts(user, until=None):
    """{'any': n, 'blue': n, 'black': n, 'double_black': n}: trails mastered at each difficulty or harder."""
    difficulties = mastered_trail_difficulties(user, until)
    counts = {'any': len(difficulties)}
    for level in (Difficulty.BLUE, Difficulty.BLACK, Difficulty.DOUBLE_BLACK):
        harder = at_least(level)
        counts[level.value] = sum(1 for d in difficulties if d in harder)
    return counts


def trails_mastered(user):
    return len(mastered_trail_difficulties(user))


def rider_stats(user):
    from .scoring import ride_streak

    rides = Ride.objects.filter(user=user)
    totals = rides.aggregate(
        rides=Count('id'), jumps=Sum('jump_count'), air=Max('biggest_air_s'), descent=Sum('descent_m'),
        climb_day=Max('climb_m'), nonstop=Max('longest_nonstop_climb_m'),
    )
    efforts = TrailEffort.objects.filter(user=user)
    most_laps = efforts.values('trail_id').annotate(n=Count('id')).aggregate(m=Max('n'))['m']
    return {
        **{k: v or 0 for k, v in totals.items()},
        'cleaned': cleaned_feature_counts(user),
        'mastered': trails_mastered(user),
        'descent_prs': efforts.filter(is_pr=True, trail__direction=Direction.DESCENT).count(),
        'climb_prs': efforts.filter(is_pr=True, trail__direction=Direction.CLIMB).count(),
        'clean_climbs': efforts.filter(touchdowns=0, trail__direction=Direction.CLIMB).count(),
        'most_laps': most_laps or 0,
        'streak': ride_streak(user),
    }


# (key, title, how to earn it, check). Keys are stored; don't rename them.
ACHIEVEMENTS = [
    ('first_ride', 'First tracks', 'Record your first ride.', lambda s: s['rides'] >= 1),
    ('first_air', 'Off the ground', 'Land your first jump.', lambda s: s['jumps'] >= 1),
    ('air_half', 'Hang time', 'Half a second of air on one jump.', lambda s: s['air'] >= 0.5),
    ('air_one', 'One-second club', 'A full second of air on one jump.', lambda s: s['air'] >= 1.0),
    ('first_feature', 'Cleaned it', 'Clean your first feature.', lambda s: s['cleaned']['any'] >= 1),
    ('blue_feature', 'Blue groove', 'Clean a blue (or harder) feature.', lambda s: s['cleaned']['blue'] >= 1),
    ('black_feature', 'Black diamond', 'Clean a feature on a black-diamond trail.',
     lambda s: s['cleaned']['black'] >= 1),
    ('double_black_feature', 'Double trouble', 'Clean a feature on a double-black trail.',
     lambda s: s['cleaned']['double_black'] >= 1),
    ('trail_mastered', 'Mastered', f'Clean every feature on a trail with {MASTERY_MIN_FEATURES} or more.',
     lambda s: s['mastered'] >= 1),
    ('first_pr', 'Personal best', 'Beat your best time on a descent.', lambda s: s['descent_prs'] >= 1),
    ('clean_climb', 'No dab', 'Ride a whole climb without putting a foot down.', lambda s: s['clean_climbs'] >= 1),
    ('climb_pr', 'Stronger', 'Beat your best time on a climb.', lambda s: s['climb_prs'] >= 1),
    ('nonstop_300', 'Engine', 'Climb 300 m without stopping to rest.', lambda s: s['nonstop'] >= 300),
    ('thousand_up', 'Thousand-metre day', 'Climb 1,000 m in one ride.', lambda s: s['climb_day'] >= 1000),
    ('vert_10k', '10K down', 'Descend 10,000 m in total.', lambda s: s['descent'] >= 10000),
    ('laps_10', 'Groundhog day', 'Ride 10 full laps of one trail.', lambda s: s['most_laps'] >= 10),
    ('streak_4', 'Habit', 'Ride 4 weeks in a row.', lambda s: s['streak'] >= 4),
]


def award(user):
    """Save any achievements the rider has newly earned. Returns their keys."""
    earned = set(Achievement.objects.filter(user=user).values_list('key', flat=True))
    stats = rider_stats(user)
    new = [key for key, _, _, check in ACHIEVEMENTS if key not in earned and check(stats)]
    Achievement.objects.bulk_create([Achievement(user=user, key=key) for key in new], ignore_conflicts=True)
    return new


def describe(keys):
    titles = {key: (title, how) for key, title, how, _ in ACHIEVEMENTS}
    return [{'key': key, 'title': titles[key][0], 'description': titles[key][1]} for key in keys if key in titles]


def listing(user):
    """Every achievement, earned ones with their date, in the order above."""
    earned = dict(Achievement.objects.filter(user=user).values_list('key', 'earned_at'))
    return [
        {'key': key, 'title': title, 'description': how, 'earned_at': earned.get(key)}
        for key, title, how, _ in ACHIEVEMENTS
    ]
