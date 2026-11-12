"""Speed rank, trends and the Progress screen.

Rider level is XP now (progression app): this module keeps the ride trends shown under it. Flow is shown as the
rider's own trend, never ranked.
"""
from datetime import timedelta

from django.db.models import Avg, Count, Max, Min, Sum
from django.utils import timezone

from progression import feature_points, ride_xp, summary
from trails import progress as feature_progress
from trails.models import Direction

from . import achievements
from .models import Ride, TrailEffort

FLOW_WEEKS = 8


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


def progress(user):
    achievements.award(user)  # also backfills riders who earned something before it existed
    feature_points.catch_up(user)  # pays out features certified since the rider logged them
    now = timezone.now()
    today = timezone.localdate()
    flow = flow_trend(user, today)
    scored = [w['flow'] for w in flow if w['flow'] is not None]
    month_start = today.replace(day=1)
    this_week = today - timedelta(days=today.weekday())
    week_rides = Ride.objects.filter(user=user, started_at__date__gte=this_week)
    week_totals = week_rides.aggregate(distance=Sum('distance_m'), descent=Sum('descent_m'), climb=Sum('climb_m'))
    return {
        **summary.dashboard(user, today),
        'flow_weeks': flow,
        'flow_avg': round(sum(scored) / len(scored)) if scored else None,
        'favorite_trail': favorite_trail(user),
        'favorite_climb': favorite_trail(user, Direction.CLIMB),
        'climbing': climbing_trend(user, today),
        'totals': {
            'features_cleaned': len(feature_progress.cleaned_ids(user)),
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
