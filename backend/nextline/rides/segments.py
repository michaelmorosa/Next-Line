"""Timed trail efforts, with no setup by the rider.

Every descent in a ride is either matched to a trail the rider can see, or becomes a new auto trail owned by that
rider. Riding the same descent again then matches the auto trail, so repeat trails turn into timed segments on
their own. Auto trails ridden only once stay hidden (see trails.views).
"""
from datetime import timedelta

from trails.models import Direction, Trail

from .analysis import climb_rate, count_between, downsample, flow_score, haversine, step_distances

# How close the track has to pass to a trail's start and end to count as riding it. GPS from a pocket is often
# 10-20 m off, so this is generous.
ENDPOINT_RADIUS_M = 40
# The ridden distance between the endpoints must be within this range of the trail's length, which rejects
# riding past both ends on a different route.
LENGTH_TOLERANCE = (0.7, 1.4)
# A descent already covered this much by a matched effort doesn't become a new auto trail.
COVERED_FRACTION = 0.5
TRAIL_PATH_POINTS = 150
# Lat/lng margin around the ride when looking for nearby trails (about 1 km).
NEARBY_DEGREES = 0.01


def match_trail(points, dist, trail):
    """Index ranges (start, end) where the track rides `trail` start to finish: one per full lap."""
    n = len(points)
    near_start = [haversine(p[1], p[2], trail.start_lat, trail.start_lng) for p in points]
    efforts = []
    i = 0
    while i < n:
        if near_start[i] > ENDPOINT_RADIUS_M:
            i += 1
            continue
        # Start at the closest point of this pass by the trail start.
        j = i
        best_start = i
        while j < n and near_start[j] <= ENDPOINT_RADIUS_M:
            if near_start[j] < near_start[best_start]:
                best_start = j
            j += 1
        k = best_start
        ridden = 0.0
        best_end = None
        while k + 1 < n and ridden <= trail.length_m * LENGTH_TOLERANCE[1]:
            ridden += dist[k]
            k += 1
            # Only look for the finish once most of the trail is behind us. On a loop the finish is the start,
            # and would otherwise match straight away.
            if ridden < trail.length_m * LENGTH_TOLERANCE[0]:
                continue
            to_end = haversine(points[k][1], points[k][2], trail.end_lat, trail.end_lng)
            if to_end <= ENDPOINT_RADIUS_M:
                best_end, best_d = k, to_end
                while k + 1 < n:
                    d = haversine(points[k + 1][1], points[k + 1][2], trail.end_lat, trail.end_lng)
                    if d > ENDPOINT_RADIUS_M:
                        break
                    k += 1
                    ridden += dist[k - 1]
                    if d < best_d:
                        best_end, best_d = k, d
                break
        if best_end is not None:
            length = sum(dist[best_start:best_end])
            if trail.length_m * LENGTH_TOLERANCE[0] <= length <= trail.length_m * LENGTH_TOLERANCE[1]:
                efforts.append((best_start, best_end))
                i = best_end + 1
                continue
        i = j
    return efforts


def nearby_trails(user, points):
    lats = [p[1] for p in points]
    lngs = [p[2] for p in points]
    return Trail.objects.visible_to(user).filter(
        start_lat__gte=min(lats) - NEARBY_DEGREES, start_lat__lte=max(lats) + NEARBY_DEGREES,
        start_lng__gte=min(lngs) - NEARBY_DEGREES, start_lng__lte=max(lngs) + NEARBY_DEGREES,
    )


def _overlap(a, b):
    """Fraction of range a covered by range b."""
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    span = a[1] - a[0]
    return max(0, hi - lo) / span if span else 0.0


def create_auto_trail(user, points, alts, dist, start, end, direction=Direction.DESCENT):
    number = Trail.objects.filter(owner=user, is_auto=True, direction=direction).count() + 1
    stretch = points[start:end + 1]
    return Trail.objects.create(
        name=f'Unnamed {direction.label.lower()} {number}',
        owner=user,
        is_auto=True,
        direction=direction,
        start_lat=points[start][1], start_lng=points[start][2],
        end_lat=points[end][1], end_lng=points[end][2],
        length_m=round(sum(dist[start:end]), 1),
        drop_m=round(abs(alts[start] - alts[end]), 1),
        path=[[round(p[1], 6), round(p[2], 6)] for p in downsample(stretch, TRAIL_PATH_POINTS)],
    )


def build_efforts(ride, points, alts, descents, touchdown_times=(), climbs=()):
    """Create the ride's TrailEffort rows (one per full lap), adding auto trails for new descents and climbs.

    `touchdown_times` are from analysis.find_touchdowns; each effort counts the ones during its lap.
    Returns the efforts.
    """
    from .models import TrailEffort

    if len(points) < 2:
        return []
    dist = step_distances(points)
    matches = []  # (trail, start, end)
    for trail in nearby_trails(ride.user, points):
        for start, end in match_trail(points, dist, trail):
            matches.append((trail, start, end))

    found = [(r, Direction.DESCENT) for r in descents] + [(r, Direction.CLIMB) for r in climbs]
    for (start, end), direction in sorted(found):
        if not any(_overlap((start, end), (s, e)) >= COVERED_FRACTION for _, s, e in matches):
            trail = create_auto_trail(ride.user, points, alts, dist, start, end, direction)
            matches.append((trail, start, end))
            # Later laps of this new descent in the same ride count on the same trail.
            for s, e in match_trail(points, dist, trail):
                if s > end:
                    matches.append((trail, s, e))

    efforts = []
    for trail, start, end in sorted(matches, key=lambda m: m[1]):
        elapsed = points[end][0] - points[start][0]
        if elapsed <= 0:
            continue
        started_at = ride.started_at + timedelta(seconds=points[start][0])
        climbing = trail.direction == Direction.CLIMB
        previous_best = (
            TrailEffort.objects.filter(user=ride.user, trail=trail, started_at__lt=started_at)
            .order_by('elapsed_s').values_list('elapsed_s', flat=True).first()
        )
        efforts.append(TrailEffort.objects.create(
            ride=ride,
            trail=trail,
            user=ride.user,
            start_t=points[start][0],
            elapsed_s=round(elapsed, 1),
            avg_speed=round(sum(dist[start:end]) / elapsed, 2),
            # Flow is about carrying speed downhill; climbs get a climb rate instead.
            flow_score=None if climbing else flow_score(points[start:end + 1]),
            climb_rate=climb_rate(alts[end] - alts[start], elapsed) if climbing else None,
            is_pr=previous_best is not None and elapsed < previous_best,
            touchdowns=count_between(touchdown_times, [(points[start][0], points[end][0])]),
            started_at=started_at,
        ))
    return efforts
