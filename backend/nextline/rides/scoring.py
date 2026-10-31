"""Rider level, speed rank and the Progress screen.

Rider level is built from bests and totals (features cleaned, fastest runs, biggest air, metres descended, climbs
cleaned, best climbing), so it only goes up. Descending skill drives it; climbing fitness adds a capped share, so a
strong climber can't reach the skill tiers on fitness alone. Flow is shown as the rider's own trend, never ranked.
"""
from datetime import timedelta

from django.db.models import Avg, Count, Max, Min, Sum
from django.utils import timezone

from trails.models import DIFFICULTY_WEIGHT, Direction, FeatureProgress, FeatureStatus, trusted_weight

from . import achievements, tiers
from .analysis import STAMINA_MIN_CLIMB_S
from .models import Ride, TrailEffort

# Tiers and their requirements are in rides/tiers.py.

# Rider level points.
FEATURE_POINTS = 25           # per cleaned feature, times the trail's difficulty weight
SPEED_POINTS_PER_MS = 10      # per m/s of your best average speed on each descent, times difficulty weight
SPEED_TRAILS_COUNTED = 10     # only your best descents count, so riding many easy trails isn't a shortcut
AIR_POINTS_PER_S = 400        # for your biggest air ever
JUMP_POINTS = 1               # per jump, up to JUMP_POINTS_CAP
JUMP_POINTS_CAP = 500
DESCENT_POINTS_PER_M = 1 / 50  # per metre descended, up to DESCENT_POINTS_CAP
DESCENT_POINTS_CAP = 500
CLEAN_CLIMB_POINTS = 30       # per climb segment ridden with no foot down, times the trail's difficulty weight
CLIMB_RATE_POINTS_CAP = 250   # for your best climb rate, reached at CLIMB_RATE_FOR_CAP
CLIMB_RATE_FOR_CAP = 1200     # vertical m/hour
NONSTOP_POINTS_PER_M = 0.5    # per metre of your longest non-stop climb, up to NONSTOP_POINTS_CAP
NONSTOP_POINTS_CAP = 150

FLOW_WEEKS = 8


def level_points(user, until=None):
    """Rider level as of `until` (default now), with the parts it's made of."""
    rides = Ride.objects.filter(user=user)
    # Speed points are for descending; climbing shows up in the stamina trend instead.
    efforts = TrailEffort.objects.filter(user=user, trail__direction=Direction.DESCENT)
    # Features waiting for approval earn nothing yet, so pinning and "cleaning" made-up features can't level you up.
    cleaned = FeatureProgress.objects.filter(user=user, status=FeatureStatus.CLEANED, feature__approved=True)
    if until:
        rides = rides.filter(started_at__lte=until)
        efforts = efforts.filter(started_at__lte=until)
        cleaned = cleaned.filter(first_cleaned_at__lte=until)

    features = sum(
        FEATURE_POINTS * trusted_weight(difficulty, owner)
        for difficulty, owner in cleaned.values_list('feature__trail__difficulty', 'feature__trail__owner_id')
    )
    best_speeds = efforts.values('trail_id', 'trail__difficulty', 'trail__owner_id').annotate(best=Min('elapsed_s'))
    per_trail = []
    for row in best_speeds:
        fastest = efforts.filter(trail_id=row['trail_id'], elapsed_s=row['best']).values_list('avg_speed', flat=True).first()
        per_trail.append(
            SPEED_POINTS_PER_MS * (fastest or 0) * trusted_weight(row['trail__difficulty'], row['trail__owner_id'])
        )
    speed = sum(sorted(per_trail, reverse=True)[:SPEED_TRAILS_COUNTED])

    totals = rides.aggregate(jumps=Sum('jump_count'), descent=Sum('descent_m'))
    biggest_air = max(rides.values_list('biggest_air_s', flat=True), default=0)
    air = AIR_POINTS_PER_S * biggest_air + min(JUMP_POINTS_CAP, JUMP_POINTS * (totals['jumps'] or 0))
    descent = min(DESCENT_POINTS_CAP, DESCENT_POINTS_PER_M * (totals['descent'] or 0))

    parts = {'features': features, 'speed': speed, 'air': air, 'descent': descent,
             'climbing': climbing_points(user, rides, until)}
    return round(sum(parts.values())), {k: round(v) for k, v in parts.items()}


def climbing_points(user, rides, until=None):
    """Clean climbs (skill, uncapped) plus best climb rate and longest non-stop climb (fitness, capped)."""
    clean = TrailEffort.objects.filter(user=user, trail__direction=Direction.CLIMB, touchdowns=0)
    if until:
        clean = clean.filter(started_at__lte=until)
    cleaned_climbs = clean.values('trail_id', 'trail__difficulty', 'trail__owner_id').distinct()
    skill = sum(
        CLEAN_CLIMB_POINTS * trusted_weight(c['trail__difficulty'], c['trail__owner_id']) for c in cleaned_climbs
    )
    # Only rides with real climbing, so one short steep burst can't set the best rate.
    best_rate = rides.filter(climb_time_s__gte=STAMINA_MIN_CLIMB_S).aggregate(m=Max('climb_rate'))['m'] or 0
    rate = min(CLIMB_RATE_POINTS_CAP, CLIMB_RATE_POINTS_CAP * best_rate / CLIMB_RATE_FOR_CAP)
    longest = rides.aggregate(m=Max('longest_nonstop_climb_m'))['m'] or 0
    nonstop = min(NONSTOP_POINTS_CAP, NONSTOP_POINTS_PER_M * longest)
    return skill + rate + nonstop


def level_summary(user):
    points, parts = level_points(user)
    month_ago = level_points(user, until=timezone.now() - timedelta(days=30))[0]
    stats = tiers.requirement_stats(user)
    index = tiers.tier_index(points, stats)
    summary = {
        'points': points,
        'tier': tiers.TIERS[index][1],
        'tier_number': index + 1,
        'tier_count': len(tiers.TIERS),
        'next_tier': None,
        'next_tier_points': None,
        'to_next': None,  # points still needed for the next tier; 0 once the points are there
        'requirements': [],  # what else the next tier needs: [{kind, difficulty, label, needed, have, met}]
        'gain_30d': points - month_ago,
        'parts': parts,
    }
    if index + 1 < len(tiers.TIERS):
        threshold, name, requirements = tiers.TIERS[index + 1]
        summary.update({
            'next_tier': name, 'next_tier_points': threshold, 'to_next': max(0, threshold - points),
            'requirements': tiers.requirement_progress(requirements, stats),
        })
    return summary


def speed_rank(ride):
    """'Top N%' across the ride's efforts, against other riders' bests on the same trails. None without rivals."""
    percents = []
    for effort in ride.efforts.select_related('trail'):
        others = (
            TrailEffort.objects.filter(trail=effort.trail).exclude(user=ride.user)
            .values('user').annotate(best=Min('elapsed_s'))
        )
        total = len(others)
        if not total:
            continue
        faster = sum(1 for row in others if row['best'] < effort.elapsed_s)
        percents.append(100 * (faster + 1) / (total + 1))
    if not percents:
        return None
    return round(sum(percents) / len(percents))


def week_start(dt):
    day = timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()
    return day - timedelta(days=day.weekday())


def ride_streak(user, today=None):
    """Consecutive weeks with at least one ride, counting back from this week (or last, if none yet this week)."""
    today = today or timezone.localdate()
    weeks = {week_start(dt) for dt in Ride.objects.filter(user=user).values_list('started_at', flat=True)}
    current = today - timedelta(days=today.weekday())
    if current not in weeks:
        current -= timedelta(weeks=1)
    streak = 0
    while current in weeks:
        streak += 1
        current -= timedelta(weeks=1)
    return streak


def flow_trend(user, today=None):
    today = today or timezone.localdate()
    this_week = today - timedelta(days=today.weekday())
    first = this_week - timedelta(weeks=FLOW_WEEKS - 1)
    by_week = {}
    for started_at, flow in Ride.objects.filter(
        user=user, flow_score__isnull=False, started_at__date__gte=first,
    ).values_list('started_at', 'flow_score'):
        by_week.setdefault(week_start(started_at), []).append(flow)
    weeks = []
    for i in range(FLOW_WEEKS):
        start = first + timedelta(weeks=i)
        scores = by_week.get(start)
        weeks.append({'week_start': start, 'flow': round(sum(scores) / len(scores)) if scores else None})
    return weeks


def favorite_trail(user, direction=Direction.DESCENT):
    """The descent (or climb) ridden most, at least twice, with every time on it, oldest first."""
    top = (
        TrailEffort.objects.filter(user=user, trail__direction=direction).values('trail_id', 'trail__name')
        .annotate(n=Count('id')).filter(n__gte=2).order_by('-n', 'trail__name').first()
    )
    if not top:
        return None
    times = list(
        TrailEffort.objects.filter(user=user, trail_id=top['trail_id'])
        .order_by('started_at').values('started_at', 'elapsed_s', 'climb_rate')
    )
    return {
        'id': top['trail_id'],
        'name': top['trail__name'],
        'efforts': times,
        'first_s': times[0]['elapsed_s'],
        'best_s': min(t['elapsed_s'] for t in times),
        'latest_s': times[-1]['elapsed_s'],
    }


def climbing_trend(user, today=None):
    """Climbing stamina by week (8 weeks) plus bests: climb rate, pace held, longest non-stop climb."""
    today = today or timezone.localdate()
    this_week = today - timedelta(days=today.weekday())
    first = this_week - timedelta(weeks=FLOW_WEEKS - 1)
    rides = Ride.objects.filter(user=user, climb_time_s__gt=0)
    by_week = {}
    for ride in rides.filter(started_at__date__gte=first).values(
        'started_at', 'climb_rate', 'climb_pace_held', 'longest_nonstop_climb_m',
    ):
        by_week.setdefault(week_start(ride['started_at']), []).append(ride)

    def avg(rows, key):
        values = [r[key] for r in rows if r[key] is not None]
        return round(sum(values) / len(values)) if values else None

    weeks = []
    for i in range(FLOW_WEEKS):
        start = first + timedelta(weeks=i)
        rows = by_week.get(start, [])
        weeks.append({
            'week_start': start,
            'climb_rate': avg(rows, 'climb_rate'),
            'pace_held': avg(rows, 'climb_pace_held'),
            'longest_nonstop_m': round(max((r['longest_nonstop_climb_m'] for r in rows), default=0)) or None,
        })
    latest = rides.order_by('-started_at').values('climb_rate', 'climb_pace_held', 'longest_nonstop_climb_m').first()
    return {
        'weeks': weeks,
        'latest': latest,
        'best_climb_rate': rides.aggregate(m=Max('climb_rate'))['m'],
        'longest_nonstop_m': round(rides.aggregate(m=Max('longest_nonstop_climb_m'))['m'] or 0),
    }


def next_milestone(level):
    if not level['next_tier']:
        return "You're at the top tier. Keep stacking features and PRs."
    todo = [f"{r['label']} ({r['have']}/{r['needed']})" for r in level['requirements'] if not r['met']]
    if todo:
        needs = '; '.join(todo)
        if level['to_next'] == 0:
            return f"You have the points for {level['next_tier']}. Still needed: {needs}."
        return f"{level['to_next']:,} points to {level['next_tier']}, plus: {needs}."
    black = FEATURE_POINTS * DIFFICULTY_WEIGHT['black']
    features_needed = max(1, -(-level['to_next'] // int(black)))
    plural = 's' if features_needed != 1 else ''
    return (
        f"{level['to_next']:,} points to {level['next_tier']}: about {features_needed} black-diamond "
        f"feature{plural}, or new PRs and bigger air."
    )


def progress(user):
    achievements.award(user)  # also backfills riders who earned something before it existed
    now = timezone.now()
    today = timezone.localdate()
    level = level_summary(user)
    flow = flow_trend(user, today)
    scored = [w['flow'] for w in flow if w['flow'] is not None]
    month_start = today.replace(day=1)
    this_week = today - timedelta(days=today.weekday())
    week_rides = Ride.objects.filter(user=user, started_at__date__gte=this_week)
    week_totals = week_rides.aggregate(distance=Sum('distance_m'), descent=Sum('descent_m'), climb=Sum('climb_m'))
    return {
        'level': level,
        'flow_weeks': flow,
        'flow_avg': round(sum(scored) / len(scored)) if scored else None,
        'favorite_trail': favorite_trail(user),
        'favorite_climb': favorite_trail(user, Direction.CLIMB),
        'climbing': climbing_trend(user, today),
        'totals': {
            'features_cleaned': FeatureProgress.objects.filter(user=user, status=FeatureStatus.CLEANED).count(),
            'air_this_month_s': round(
                Ride.objects.filter(user=user, started_at__date__gte=month_start)
                .aggregate(s=Sum('total_air_s'))['s'] or 0, 1),
            'streak_weeks': ride_streak(user, today),
            'rides_this_week': week_rides.count(),
            'distance_this_week_m': round(week_totals['distance'] or 0),
            'descent_this_week_m': round(week_totals['descent'] or 0),
            'climb_this_week_m': round(week_totals['climb'] or 0),
            'rides': Ride.objects.filter(user=user).count(),
        },
        'next_milestone': next_milestone(level),
        'achievements': achievements.listing(user),
        'generated_at': now,
    }


def average_flow_before(ride):
    return Ride.objects.filter(
        user=ride.user, started_at__lt=ride.started_at, flow_score__isnull=False,
    ).aggregate(a=Avg('flow_score'))['a']


def biggest_air_before(ride):
    return max(
        Ride.objects.filter(user=ride.user, started_at__lt=ride.started_at).values_list('biggest_air_s', flat=True),
        default=0,
    )
