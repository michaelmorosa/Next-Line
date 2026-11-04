"""XP from riding: the ride itself, metres descended, jumps, PRs, biggest air, clean climbs and cleaned features.

Ride entries have sources starting 'ride:<id>' and are dated when the ride started, so deleting a ride can undo
exactly what it earned, and daily caps group by the day ridden. award_ride() and award_features() are safe to run
any number of times, which is how backfill_xp works.
"""
from datetime import timedelta

from django.db.models import Sum

from rides.models import Ride, TrailEffort
from trails.models import Direction, FeatureProgress, FeatureStatus, trusted_weight

from . import content, xp
from .models import Reason, XPEntry


def ride_source(ride, *parts):
    return ':'.join(['ride', str(ride.id), *map(str, parts)])


def capped_today(ride, reason, earned, cap):
    """`earned`, cut down so the rider's `reason` XP for the day the ride started stays within `cap`."""
    day = ride.started_at.date()
    so_far = XPEntry.objects.filter(
        user=ride.user, reason=reason, created_at__date=day,
    ).exclude(source__startswith=ride_source(ride) + ':').aggregate(t=Sum('amount'))['t'] or 0
    return max(0, min(earned, cap - so_far))


def award_ride(ride):
    """Everything an uploaded ride earned. Returns the new ledger entries."""
    rules = content.rules()
    values, caps = rules['xp'], rules['caps']
    user, at = ride.user, ride.started_at
    awards = [xp.award(user, Reason.RIDE, ride_source(ride), values['ride'], at=at)]

    descent = int(ride.descent_m // 100) * values['descent_per_100m']
    awards.append(xp.award(user, Reason.DESCENT, ride_source(ride, 'descent'),
                           capped_today(ride, Reason.DESCENT, descent, caps['descent_xp_per_day']), at=at))
    jumps = ride.jump_count * values['jump']
    awards.append(xp.award(user, Reason.JUMPS, ride_source(ride, 'jumps'),
                           capped_today(ride, Reason.JUMPS, jumps, caps['jump_xp_per_day']), at=at))

    biggest_before = max(
        Ride.objects.filter(user=user, started_at__lt=ride.started_at).values_list('biggest_air_s', flat=True),
        default=0,
    )
    if ride.biggest_air_s > biggest_before:
        awards.append(xp.award(user, Reason.AIR, ride_source(ride, 'air'), values['biggest_air'], at=at))

    for effort in ride.efforts.select_related('trail'):
        trail = effort.trail
        if effort.is_pr:
            awards.append(xp.award(user, Reason.PR, ride_source(ride, 'pr', trail.id), values['trail_pr'], at=at))
        if trail.direction == Direction.CLIMB and effort.touchdowns == 0 and not TrailEffort.objects.filter(
            user=user, trail=trail, touchdowns=0, started_at__lt=effort.started_at,
        ).exists():
            amount = round(values['clean_climb_per_weight'] * trusted_weight(trail.difficulty, trail.owner_id))
            awards.append(xp.award(user, Reason.CLEAN_CLIMB, ride_source(ride, 'clean_climb', trail.id), amount,
                                   at=at))
    return [a for a in awards if a]


def undo_ride(ride):
    """Correction entries cancelling what a ride earned, before it's deleted."""
    for entry in XPEntry.objects.filter(user=ride.user, source__startswith=ride_source(ride) + ':') | \
            XPEntry.objects.filter(user=ride.user, source=ride_source(ride)):
        xp.award(ride.user, Reason.CORRECTION, f'undo:{entry.source}', -entry.amount, skill_id=entry.skill_id)


def award_features(user):
    """XP for every approved feature the rider has cleaned and not been paid for yet, weighted by the trail's
    trusted difficulty. Pins waiting for approval pay out once they're approved."""
    per_weight = content.rules()['xp']['feature_cleaned_per_weight']
    cleaned = FeatureProgress.objects.filter(
        user=user, status=FeatureStatus.CLEANED, feature__approved=True,
    ).select_related('feature__trail')
    paid = set(XPEntry.objects.filter(user=user, reason=Reason.FEATURE).values_list('source', flat=True))
    awards = []
    for progress in cleaned:
        source = f'feature:{progress.feature_id}'
        if source in paid:
            continue
        trail = progress.feature.trail
        amount = round(per_weight * trusted_weight(trail.difficulty, trail.owner_id))
        awards.append(xp.award(user, Reason.FEATURE, source, amount, at=progress.first_cleaned_at))
    return [a for a in awards if a]


def ride_xp(ride):
    """What a ride earned, for the ride summary: {xp, items: [{label, amount}], level_before, level, leveled_up}."""
    entries = list(XPEntry.objects.filter(user=ride.user, source__startswith=ride_source(ride) + ':'))
    entries += XPEntry.objects.filter(user=ride.user, source=ride_source(ride))
    first_cleaned = FeatureProgress.objects.filter(
        user=ride.user, feature_id__in=ride.cleaned_features, first_cleaned_at=ride.started_at,
    ).values_list('feature_id', flat=True)
    entries += XPEntry.objects.filter(user=ride.user, source__in=[f'feature:{f}' for f in first_cleaned])
    gained = sum(e.amount for e in entries)
    before = xp.level_for(xp.total_xp(ride.user, until=ride.started_at - timedelta(microseconds=1)))
    after = xp.level_for(before['total'] + gained)
    by_reason = {}
    for e in entries:
        by_reason[e.get_reason_display()] = by_reason.get(e.get_reason_display(), 0) + e.amount
    return {
        'xp': gained,
        'items': [{'label': label, 'amount': amount} for label, amount in by_reason.items() if amount],
        'level_before': before,
        'level': after,
        'leveled_up': after['level'] > before['level'],
    }
