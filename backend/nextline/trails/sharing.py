"""Making a rider's trail shared, and folding other riders' private copies of it into the shared one.

Each rider gets a private auto trail for every descent and climb they ride. When a trail is promoted to shared,
everyone who already rode it has their own copy, and their future rides would be timed on both. promote() merges
those copies into the shared trail: laps, PRs and features carry over, and the copies are deleted.
"""
from django.db import transaction

from rides.analysis import haversine

from .models import Feature, FeatureProgress, FeatureStatus, Trail

# A private trail is a copy of the shared one when both ends are this close and the lengths roughly agree. Auto
# trails start and end where each rider's GPS said the elevation started changing, so this is looser than matching.
COPY_ENDPOINT_RADIUS_M = 60
COPY_LENGTH_RATIO = (0.75, 1.33)
# About 100 m of latitude/longitude, to narrow the search before measuring distances.
COPY_SEARCH_DEGREES = 0.001
# A copy's feature this close to one on the shared trail is the same feature.
SAME_FEATURE_RADIUS_M = 15
# Two laps on the same trail in the same ride starting this close together are the same lap counted twice.
SAME_LAP_S = 30

STATUS_RANK = {FeatureStatus.LOCKED: 0, FeatureStatus.ALMOST: 1, FeatureStatus.CLEANED: 2}


def find_copies(trail):
    """Riders' private trails that are the same descent or climb as `trail`."""
    d = COPY_SEARCH_DEGREES
    candidates = Trail.objects.filter(
        owner__isnull=False, direction=trail.direction,
        start_lat__range=(trail.start_lat - d, trail.start_lat + d),
        start_lng__range=(trail.start_lng - d, trail.start_lng + d),
    ).exclude(pk=trail.pk)
    return [
        c for c in candidates
        if haversine(c.start_lat, c.start_lng, trail.start_lat, trail.start_lng) <= COPY_ENDPOINT_RADIUS_M
        and haversine(c.end_lat, c.end_lng, trail.end_lat, trail.end_lng) <= COPY_ENDPOINT_RADIUS_M
        and COPY_LENGTH_RATIO[0] <= c.length_m / trail.length_m <= COPY_LENGTH_RATIO[1]
    ]


def merge_progress(source, target):
    """Fold one feature's rider progress into another's, keeping each rider's best."""
    for progress in FeatureProgress.objects.filter(feature=source):
        existing = FeatureProgress.objects.filter(user=progress.user, feature=target).first()
        if not existing:
            progress.feature = target
            progress.save(update_fields=['feature'])
            continue
        if STATUS_RANK[progress.status] > STATUS_RANK[existing.status]:
            existing.status = progress.status
        existing.clean_count = max(existing.clean_count, progress.clean_count)
        firsts = [t for t in (existing.first_cleaned_at, progress.first_cleaned_at) if t]
        existing.first_cleaned_at = min(firsts) if firsts else None
        existing.note = existing.note or progress.note
        existing.save()
        progress.delete()


def remap_cleaned(source, target):
    """Point rides' check-ins at the surviving feature, so editing an old check-in still adjusts the right count."""
    from rides.models import Ride

    users = set(FeatureProgress.objects.filter(feature__in=[source, target]).values_list('user_id', flat=True))
    users.add(source.created_by_id)
    for ride in Ride.objects.filter(user_id__in=users).exclude(cleaned_features=[]):
        if source.id in ride.cleaned_features:
            ride.cleaned_features = sorted({target.id if i == source.id else i for i in ride.cleaned_features})
            ride.save(update_fields=['cleaned_features'])


def move_features(copy, shared):
    """Move a copy's features to the shared trail. Returns (moved, merged)."""
    moved = merged = 0
    for feature in list(copy.features.all()):
        same = next((
            f for f in shared.features.all()
            if haversine(f.lat, f.lng, feature.lat, feature.lng) <= SAME_FEATURE_RADIUS_M
        ), None)
        if same:
            remap_cleaned(feature, same)
            merge_progress(feature, same)
            feature.delete()
            merged += 1
        else:
            feature.trail = shared
            feature.save(update_fields=['trail'])
            moved += 1
    return moved, merged


def remove_double_laps(trail):
    """After moving laps, a ride timed on both the copy and the shared trail has the same lap twice."""
    from rides.models import TrailEffort

    removed = 0
    seen = {}
    for effort in TrailEffort.objects.filter(trail=trail).order_by('ride_id', 'start_t'):
        previous = seen.get(effort.ride_id)
        if previous is not None and abs(effort.start_t - previous) <= SAME_LAP_S:
            effort.delete()
            removed += 1
            continue
        seen[effort.ride_id] = effort.start_t
    return removed


def recompute_prs(trail):
    """A lap is a PR when it beats every earlier lap by the same rider on this trail."""
    from rides.models import TrailEffort

    best = {}
    for effort in TrailEffort.objects.filter(trail=trail).order_by('started_at'):
        previous = best.get(effort.user_id)
        is_pr = previous is not None and effort.elapsed_s < previous
        if effort.is_pr != is_pr:
            effort.is_pr = is_pr
            effort.save(update_fields=['is_pr'])
        best[effort.user_id] = effort.elapsed_s if previous is None else min(previous, effort.elapsed_s)


@transaction.atomic
def merge_feature(feature, target):
    """Fold a duplicate pin into an existing feature: riders' progress and check-ins move over, the pin goes."""
    remap_cleaned(feature, target)
    merge_progress(feature, target)
    feature.delete()


@transaction.atomic
def promote(trail):
    """Make `trail` shared and merge riders' copies of it. Returns counts for the admin message."""
    from rides.models import TrailEffort

    copies = find_copies(trail)
    laps = TrailEffort.objects.filter(trail__in=copies).update(trail=trail)
    moved = merged = 0
    for copy in copies:
        m, g = move_features(copy, trail)
        moved += m
        merged += g
    riders = len({c.owner_id for c in copies})
    Trail.objects.filter(pk__in=[c.pk for c in copies]).delete()

    trail.owner = None
    trail.is_auto = False
    trail.save(update_fields=['owner', 'is_auto'])
    # Riders' pins are now on a trail everyone sees: they wait for approval like any other pin on a shared trail.
    pending = trail.features.filter(approved=True).exclude(created_by__is_staff=True).update(approved=False)
    double = remove_double_laps(trail)
    recompute_prs(trail)
    return {'copies': len(copies), 'riders': riders, 'laps': laps - double, 'features_moved': moved,
            'features_merged': merged, 'features_pending': pending}
