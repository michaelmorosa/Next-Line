"""Turn an uploaded recording into a scored ride."""
from django.conf import settings
from django.db import transaction

from trails.models import Direction

from . import analysis
from .models import Jump, Ride
from .segments import build_efforts

# Stored tracks are thinned to this many points; full-resolution tracks are only used while processing.
STORED_TRACK_POINTS = 3000
# The phone flags anything from a hop off a root upward; shorter "airtime" is noise from the rider's own movement.
MIN_AIRTIME_S = 0.15
MAX_AIRTIME_S = 3.0
CLIMB_FIELDS = ('climb_time_s', 'descent_time_s', 'climb_rate', 'longest_nonstop_climb_m', 'climb_rests',
                'climb_pace_held')


@transaction.atomic
def create_ride(user, client_id, started_at, elapsed_s, track, jumps, title=''):
    """Save and score a ride. `track` is raw [t, lat, lng, alt, speed] points; `jumps` is [{t, airtime_s}]."""
    points = analysis.clean_track(track[: settings.MAX_TRACK_POINTS])
    summary = analysis.summarize(points) if len(points) >= 2 else None

    jumps = sorted(
        (j for j in jumps if MIN_AIRTIME_S <= j['airtime_s'] <= MAX_AIRTIME_S),
        key=lambda j: j['t'],
    )
    airtimes = [j['airtime_s'] for j in jumps]

    ride = Ride.objects.create(
        user=user,
        client_id=client_id,
        title=title,
        started_at=started_at,
        elapsed_s=elapsed_s,
        moving_s=summary['moving_s'] if summary else 0,
        distance_m=summary['distance_m'] if summary else 0,
        climb_m=summary['climb_m'] if summary else 0,
        descent_m=summary['descent_m'] if summary else 0,
        max_speed=summary['max_speed'] if summary else 0,
        flow_score=summary['flow_score'] if summary else None,
        **({k: summary[k] for k in CLIMB_FIELDS} if summary else {}),
        track=[
            [round(p[0], 1), round(p[1], 6), round(p[2], 6),
             None if p[3] is None else round(p[3], 1), round(p[4], 2)]
            for p in analysis.downsample(points, STORED_TRACK_POINTS)
        ],
        jump_count=len(jumps),
        total_air_s=round(sum(airtimes), 2),
        biggest_air_s=round(max(airtimes, default=0), 2),
    )

    Jump.objects.bulk_create([
        Jump(ride=ride, t=j['t'], airtime_s=round(j['airtime_s'], 2),
             **dict(zip(('lat', 'lng'), analysis.position_at(points, j['t']) or (None, None))))
        for j in jumps
    ])

    if summary:
        touchdown_times = analysis.find_touchdowns(points)
        efforts = build_efforts(
            ride, points, summary['alts'], summary['descents'], touchdown_times, summary['climbs'],
        )
        # Touchdowns count on descents and timed laps, climbs included (cleaning a technical climb is a goal),
        # not on the fire roads and flats between them.
        ranges = [(points[s][0], points[e][0]) for s, e in summary['descents']]
        ranges += [(e.start_t, e.start_t + e.elapsed_s) for e in efforts]
        ride.touchdowns_detected = analysis.count_between(touchdown_times, ranges)
        if not title and efforts:
            # Name the ride after its longest descent: climbs take longer but aren't what a ride is remembered by.
            named = [e for e in efforts if e.trail.direction == Direction.DESCENT] or efforts
            ride.title = max(named, key=lambda e: e.elapsed_s).trail.name
        ride.save(update_fields=['title', 'touchdowns_detected'])
    return ride
