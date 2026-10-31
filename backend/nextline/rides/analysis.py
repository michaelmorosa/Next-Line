"""Ride statistics from a GPS track. Pure functions, no database.

A track is a list of points [t, lat, lng, alt, speed]: seconds since the ride started, degrees, metres above sea
level (or None), and metres per second (or None, in which case it's worked out from the positions).

The phone is in a pocket, so everything here has to cope with GPS noise: altitude is smoothed before climbs and
descents are counted, and small wobbles in a descent don't split it in two.
"""
import math

EARTH_RADIUS_M = 6371000

# Below this the rider counts as stopped (walking pace is about 1.4 m/s), so stops don't count as moving time.
MOVING_SPEED = 1.0
# A gap between points longer than this is a GPS dropout or a pause, never moving time.
MAX_MOVING_GAP_S = 30
# 126 km/h. Faster than any rider; anything above is a bad GPS fix.
MAX_PLAUSIBLE_SPEED = 35
# Climb/descent totals ignore altitude changes smaller than this, which are mostly GPS noise.
ELEVATION_NOISE_M = 3.0

# What counts as a descent or climb worth timing. Both need this much elevation change over this distance.
SEGMENT_MIN_ELEVATION_M = 30
SEGMENT_MIN_LENGTH_M = 200
DESCENT_MIN_DURATION_S = 20
CLIMB_MIN_DURATION_S = 30
# Faster than this (vertical m/hour) is a chairlift or shuttle, not pedalling. Strong riders manage about 1800.
CLIMB_MAX_RATE = 2000
# A descent may climb this much (a short pedal-up or a GPS wobble) without ending, and a climb may dip this much.
SEGMENT_MAX_REVERSAL_M = 8
# A segment starts once the rider is this far from the high (or low) point, and its ends are trimmed to where the
# elevation really starts and stops changing.
SEGMENT_TRIGGER_M = 4
SEGMENT_TRIM_M = 2

# Touchdowns (a foot down). A pocketed phone can't feel the foot, but it can see the rider nearly stop and set off
# again, which on technical terrain is almost always a dab. Longer stops are rests, not touchdowns.
TOUCHDOWN_SPEED = 0.8
TOUCHDOWN_RESUME_SPEED = 1.5
TOUCHDOWN_MIN_PRIOR_SPEED = 2.0
TOUCHDOWN_MAX_S = 15

# Pace held (climbing stamina) needs this much climbing in a ride to compare the first half with the second.
STAMINA_MIN_CLIMB_S = 240

# Flow needs a reasonably long, moving stretch to mean anything.
FLOW_MIN_POINTS = 10
FLOW_MIN_AVG_SPEED = 2.0


def haversine(lat1, lng1, lat2, lng2):
    """Distance in metres between two points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def clean_track(points):
    """Valid points in time order, with every speed filled in and GPS jumps removed."""
    out = []
    for p in sorted(points, key=lambda p: p[0]):
        t, lat, lng = p[0], p[1], p[2]
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        alt = p[3] if len(p) > 3 else None
        speed = p[4] if len(p) > 4 else None
        if out:
            prev = out[-1]
            if t <= prev[0]:
                continue
            implied = haversine(prev[1], prev[2], lat, lng) / (t - prev[0])
            # A position that implies riding faster than this is a GPS glitch, not the rider.
            if implied > MAX_PLAUSIBLE_SPEED:
                continue
            if speed is None or speed < 0 or speed > MAX_PLAUSIBLE_SPEED:
                speed = implied
        elif speed is None or speed < 0 or speed > MAX_PLAUSIBLE_SPEED:
            speed = 0.0
        out.append([t, lat, lng, alt, speed])
    return out


def step_distances(points):
    """Distance from each point to the next."""
    return [haversine(a[1], a[2], b[1], b[2]) for a, b in zip(points, points[1:])]


def smoothed_altitudes(points, window=5):
    """Centered moving average of altitude. Missing altitudes are filled from the nearest known one."""
    alts = [p[3] for p in points]
    known = [a for a in alts if a is not None]
    if not known:
        return [0.0] * len(points)
    last = known[0]
    filled = []
    for a in alts:
        if a is not None:
            last = a
        filled.append(last)
    half = window // 2
    out = []
    for i in range(len(filled)):
        lo, hi = max(0, i - half), min(len(filled), i + half + 1)
        out.append(sum(filled[lo:hi]) / (hi - lo))
    return out


def elevation_totals(alts, noise=ELEVATION_NOISE_M):
    """(climb, descent) in metres, counting a change only once it exceeds `noise`."""
    if not alts:
        return 0.0, 0.0
    climb = descent = 0.0
    ref = alts[0]
    for a in alts[1:]:
        if a - ref >= noise:
            climb += a - ref
            ref = a
        elif ref - a >= noise:
            descent += ref - a
            ref = a
    return climb, descent


def moving_time(points):
    total = 0.0
    for a, b in zip(points, points[1:]):
        dt = b[0] - a[0]
        if dt <= MAX_MOVING_GAP_S and b[4] >= MOVING_SPEED:
            total += dt
    return total


def _find_drops(points, alts, min_duration):
    """Index ranges (start, end) where `alts` drops enough to time. Climbs use this with altitude flipped."""
    n = len(points)
    found = []
    peak = 0
    trough = None
    j = 1
    while j < n:
        if trough is None:
            if alts[j] >= alts[peak]:
                peak = j
            elif alts[peak] - alts[j] >= SEGMENT_TRIGGER_M:
                trough = j
        else:
            if alts[j] < alts[trough]:
                trough = j
            elif alts[j] - alts[trough] > SEGMENT_MAX_REVERSAL_M:
                found.append((peak, trough))
                # Look for the next high point from the bottom of this drop.
                peak = max(range(trough, j + 1), key=lambda k: alts[k])
                trough = None
        j += 1
    if trough is not None:
        found.append((peak, trough))

    dist = step_distances(points)
    ranges = []
    for start, end in found:
        top, bottom = alts[start], alts[end]
        if top - bottom < SEGMENT_MIN_ELEVATION_M:
            continue
        # Skip the flat at the top and the run-out at the bottom.
        while start < end and alts[start + 1] >= top - SEGMENT_TRIM_M:
            start += 1
        while end > start and alts[end - 1] <= bottom + SEGMENT_TRIM_M:
            end -= 1
        if points[end][0] - points[start][0] < min_duration:
            continue
        if sum(dist[start:end]) < SEGMENT_MIN_LENGTH_M:
            continue
        ranges.append((start, end))
    return ranges


def find_descents(points, alts=None):
    """Index ranges (start, end) of the descents in a track, each long and steep enough to time."""
    if alts is None:
        alts = smoothed_altitudes(points)
    return _find_drops(points, alts, DESCENT_MIN_DURATION_S)


def find_climbs(points, alts=None):
    """Index ranges (start, end) of the climbs in a track, each long and steep enough to time."""
    if alts is None:
        alts = smoothed_altitudes(points)
    climbs = []
    for start, end in _find_drops(points, [-a for a in alts], CLIMB_MIN_DURATION_S):
        # A GPS gap mid-climb is usually a shuttle or the phone losing signal; neither is a climb to time.
        if any(points[i + 1][0] - points[i][0] > MAX_MOVING_GAP_S for i in range(start, end)):
            continue
        if (climb_rate(alts[end] - alts[start], points[end][0] - points[start][0]) or 0) > CLIMB_MAX_RATE:
            continue
        climbs.append((start, end))
    return climbs


def climbing_stamina(points, alts, climbs):
    """How well the rider kept climbing: longest non-stop climb, rests, and pace held through the ride.

    A rest is a stop of TOUCHDOWN_MAX_S or longer; anything shorter is a dab, not a rest. Pace held compares the
    climb rate over the second half of the ride's climbing time with the first half, as a percentage; it's None
    when there wasn't enough climbing to compare.
    """
    longest = 0.0
    rests = 0
    steps = []  # (seconds, metres gained) for every step on a climb, in ride order
    for start, end in climbs:
        nonstop_from = start
        stopped_at = None
        for i in range(start, end + 1):
            if points[i][4] < MOVING_SPEED:
                if stopped_at is None:
                    stopped_at = i
            elif stopped_at is not None:
                if points[i][0] - points[stopped_at][0] >= TOUCHDOWN_MAX_S:
                    rests += 1
                    longest = max(longest, alts[stopped_at] - alts[nonstop_from])
                    nonstop_from = i
                stopped_at = None
        longest = max(longest, alts[end] - alts[nonstop_from])
        steps += [(points[i + 1][0] - points[i][0], alts[i + 1] - alts[i]) for i in range(start, end)]

    total = sum(dt for dt, _ in steps)
    pace_held = None
    if total >= STAMINA_MIN_CLIMB_S:
        halves = [[0.0, 0.0], [0.0, 0.0]]
        elapsed = 0.0
        for dt, gain in steps:
            half = halves[0 if elapsed < total / 2 else 1]
            half[0] += dt
            half[1] += gain
            elapsed += dt
        first, second = (climb_rate(g, t) for t, g in halves)
        if first and second:
            pace_held = round(100 * second / first)
    return {'longest_nonstop_climb_m': round(max(0.0, longest), 1), 'climb_rests': rests, 'climb_pace_held': pace_held}


def climb_rate(gain_m, seconds):
    """Vertical metres climbed per hour (VAM), or None for no climbing."""
    if gain_m <= 0 or seconds <= 0:
        return None
    return round(gain_m / seconds * 3600)


def flow_score(points):
    """0-100: how steady the rider's speed was. 100 means no speed changes at all.

    From a pocket, speed steadiness is the most reliable flow signal: braking hard into corners and sprinting out
    shows up as big speed swings. Scored as 100 * (1 - coefficient of variation of speed).
    """
    speeds = [p[4] for p in points]
    if len(speeds) < FLOW_MIN_POINTS:
        return None
    mean = sum(speeds) / len(speeds)
    if mean < FLOW_MIN_AVG_SPEED:
        return None
    std = math.sqrt(sum((s - mean) ** 2 for s in speeds) / len(speeds))
    return round(max(0.0, min(100.0, 100 * (1 - std / mean))), 1)


def find_touchdowns(points):
    """Times (t) the rider stalled while riding and set off again soon after: an estimate of feet put down.

    A stall that never resumes (the end of the track) or lasts longer than TOUCHDOWN_MAX_S isn't counted.
    """
    found = []
    riding = False
    i = 0
    n = len(points)
    while i < n:
        speed = points[i][4]
        if speed >= TOUCHDOWN_MIN_PRIOR_SPEED:
            riding = True
        elif riding and speed < TOUCHDOWN_SPEED:
            stalled_at = points[i][0]
            j = i
            while j < n and points[j][4] < TOUCHDOWN_RESUME_SPEED:
                j += 1
            if j < n and points[j][0] - stalled_at <= TOUCHDOWN_MAX_S:
                found.append(stalled_at)
            riding = False
            i = j
            continue
        i += 1
    return found


def count_between(times, ranges):
    """How many of `times` fall inside any of the (start_t, end_t) ranges."""
    return sum(1 for t in times if any(start <= t <= end for start, end in ranges))


def weighted_flow(scored):
    """Duration-weighted average of [(flow, seconds), ...], ignoring unscored stretches."""
    scored = [(f, s) for f, s in scored if f is not None and s > 0]
    total = sum(s for _, s in scored)
    if not total:
        return None
    return round(sum(f * s for f, s in scored) / total, 1)


def downsample(points, max_points):
    if len(points) <= max_points:
        return points
    step = math.ceil(len(points) / max_points)
    out = points[::step]
    if out[-1] is not points[-1]:
        out.append(points[-1])
    return out


def position_at(points, t):
    """(lat, lng) interpolated at time t, or None outside the track."""
    if not points or t < points[0][0] or t > points[-1][0]:
        return None
    lo, hi = 0, len(points) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if points[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    a, b = points[lo], points[hi]
    span = b[0] - a[0]
    f = 0 if span == 0 else (t - a[0]) / span
    return a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f


def summarize(points):
    """Distance, time, elevation, speed and flow for a cleaned track."""
    alts = smoothed_altitudes(points)
    climb, descent = elevation_totals(alts)
    descents = find_descents(points, alts)
    climbs = find_climbs(points, alts)
    flows = [(flow_score(points[s:e + 1]), points[e][0] - points[s][0]) for s, e in descents]
    climb_time = sum(points[e][0] - points[s][0] for s, e in climbs)
    climb_gain = sum(alts[e] - alts[s] for s, e in climbs)
    return {
        'distance_m': round(sum(step_distances(points)), 1),
        'moving_s': round(moving_time(points), 1),
        'climb_m': round(climb, 1),
        'descent_m': round(descent, 1),
        'max_speed': round(max((p[4] for p in points), default=0.0), 2),
        'flow_score': weighted_flow(flows),
        'climb_time_s': round(climb_time, 1),
        'descent_time_s': round(sum(points[e][0] - points[s][0] for s, e in descents), 1),
        # Measured on the timed climbs only, so flat riding and stops between them don't drag it down.
        'climb_rate': climb_rate(climb_gain, climb_time),
        **climbing_stamina(points, alts, climbs),
        'descents': descents,
        'climbs': climbs,
        'alts': alts,
    }
