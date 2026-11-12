"""Ladders and "next up".

A ladder is every live feature of one type in a trail system, in grade order. A rung is a grade that exists in a
ladder. Next up suggests features the rider is ready for, never skipping a rung:

1. Certified (not changed, closed or draft) and not yet cleaned by the rider.
2. At most one grade above the highest grade the rider has cleaned in that type, anywhere (0 if none).
3. For every rung below it in its ladder, the rider has cleaned some feature of that grade at least
   next_up.repeat_cleans_needed times (repeat cleans of one feature count).
4. Not above next_up.advanced_above_grade unless the rider has turned on advanced features.

Grades here are the features' current grades: a rider's place on a ladder follows regrading. (Points keep the grade
at the time of the log.)
"""
from collections import defaultdict

from progression import content
from rides.models import TrailEffort

from .models import Certification, Feature, FeatureLog, FeatureType, Outcome

# Words that push riders to attempt something. Suggestion text never uses them (checked in tests).
PRESSURE_PHRASES = ('you should', 'you need to', 'you must', 'easy', 'just send', 'send it', 'no excuse', "don't be")


def type_label(type_, plural=False):
    label = FeatureType(type_).label.lower()
    return label + ('s' if plural and not label.endswith('s') else '')


class RiderRecord:
    """What a rider has done on features, by type and grade, from their logs."""

    def __init__(self, user):
        self.user = user
        self.cleans = defaultdict(int)          # feature_id -> clean count
        self.outcomes = defaultdict(set)        # feature_id -> {outcomes}
        self.rung_cleans = defaultdict(int)     # (type, grade) -> clean count
        self.rung_names = defaultdict(list)     # (type, grade) -> names of cleaned features
        self.best = defaultdict(int)            # type -> highest grade cleaned
        logs = FeatureLog.objects.filter(user=user, feature__grade__isnull=False).select_related('feature')
        for log in logs:
            f = log.feature
            self.outcomes[f.id].add(log.outcome)
            if log.outcome == Outcome.CLEANED:
                self.cleans[f.id] += 1
                self.rung_cleans[(f.type, f.grade)] += 1
                if f.name not in self.rung_names[(f.type, f.grade)]:
                    self.rung_names[(f.type, f.grade)].append(f.name)
                self.best[f.type] = max(self.best[f.type], f.grade)

    def status(self, feature_id):
        if self.cleans.get(feature_id):
            return Outcome.CLEANED.value
        seen = self.outcomes.get(feature_id, set())
        for outcome in (Outcome.SKETCHY, Outcome.WALKED):
            if outcome in seen:
                return outcome.value
        return 'not_yet'


def ladder_features(system=None, type_=None):
    """Live features in ladder order (grade, then trail, then riding order)."""
    features = Feature.objects.live().filter(grade__isnull=False).select_related('trail')
    if system is not None:
        features = features.filter(trail__system=system)
    if type_:
        features = features.filter(type=type_)
    return features.order_by('type', 'grade', 'trail__name', 'position', 'id')


def ladders(user, system):
    """Every ladder at a trail system with the rider's status on each rung:
    [{type, label, best_grade, cleaned, total, rungs: [{grade, features: [...]}]}]"""
    record = RiderRecord(user)
    by_type = defaultdict(lambda: defaultdict(list))
    for f in ladder_features(system):
        by_type[f.type][f.grade].append(f)
    out = []
    for type_ in FeatureType.values:
        if type_ not in by_type:
            continue
        rungs = []
        total = cleaned = 0
        for grade in sorted(by_type[type_]):
            row = []
            for f in by_type[type_][grade]:
                status = record.status(f.id)
                total += 1
                cleaned += status == 'cleaned'
                row.append({'id': f.id, 'name': f.name, 'trail': f.trail_id, 'trail_name': f.trail.name,
                            'grade': f.grade, 'status': status, 'certification': f.status})
            rungs.append({'grade': grade, 'features': row, 'rider_cleans': record.rung_cleans[(type_, grade)]})
        out.append({'type': type_, 'label': FeatureType(type_).label, 'best_grade': record.best[type_] or None,
                    'cleaned': cleaned, 'total': total, 'rungs': rungs})
    return out


def rules():
    return content.rules()['next_up']


def blocked_by(feature, record, rungs_below, user):
    """Why a feature isn't next up for this rider, or None if it is."""
    r = rules()
    if feature.status != Certification.CERTIFIED:
        return 'not certified'
    if record.cleans.get(feature.id):
        return 'already cleaned'
    if feature.grade > record.best[feature.type] + 1:
        return 'more than one grade above your best'
    if feature.grade > r['advanced_above_grade'] and not user.advanced_features:
        return 'advanced'
    for grade in rungs_below:
        if record.rung_cleans[(feature.type, grade)] < r['repeat_cleans_needed']:
            return f'grade {grade} not cleaned {r["repeat_cleans_needed"]} times yet'
    return None


def reason(feature, record, system_name):
    """Plain words for why this was suggested. Never pressure: next up is for when the rider's ready."""
    type_, grade = feature.type, feature.grade
    best = record.best[type_]
    where = f'on {feature.trail.name}'
    if best == 0:
        text = f'The first rung of the {type_label(type_)} ladder{f" at {system_name}" if system_name else ""}: ' \
               f'a grade {grade} {type_label(type_)} {where}.'
    elif grade == best + 1:
        cleans = record.rung_cleans[(type_, best)]
        names = ', '.join(record.rung_names[(type_, best)][:2])
        text = f"You've cleaned grade {best} {type_label(type_, plural=True)} {cleans} times ({names}). " \
               f'This is the next rung: a grade {grade} {type_label(type_)} {where}.'
    else:
        names = record.rung_names[(type_, grade)][:1]
        like = f', like {names[0]}' if names else ''
        text = f'Another grade {grade} {type_label(type_)}{like}, {where}. More time at this grade before the next.'
    if Outcome.SKETCHY in record.outcomes.get(feature.id, set()):
        text += ' You rode it sketchy last time.'
    return text


def next_up(user, system=None, limit=None):
    """Up to next_up.max_suggestions features the rider is ready for, with reasons.
    [{feature fields..., reason, step_up}]"""
    limit = limit or rules()['max_suggestions']
    record = RiderRecord(user)
    features = list(ladder_features(system).select_related('trail__system'))
    grades_in_ladder = defaultdict(set)
    for f in features:
        grades_in_ladder[(f.trail.system_id, f.type)].add(f.grade)
    ridden = set(TrailEffort.objects.filter(user=user).values_list('trail_id', flat=True))

    eligible = []
    for f in features:
        below = sorted(g for g in grades_in_ladder[(f.trail.system_id, f.type)] if g < f.grade)
        if blocked_by(f, record, below, user) is None:
            eligible.append(f)

    def rank(f):
        sketchy = Outcome.SKETCHY in record.outcomes.get(f.id, set())
        step_up = f.grade == record.best[f.type] + 1
        return (not sketchy, not step_up, f.trail_id not in ridden, f.grade, f.trail.name, f.position)

    eligible.sort(key=rank)
    picked, types = [], set()
    for f in eligible:  # one per type first, so suggestions are varied
        if f.type not in types:
            picked.append(f)
            types.add(f.type)
    for f in eligible:
        if f not in picked:
            picked.append(f)
    return [
        {'feature': f, 'reason': reason(f, record, f.trail.system.name if f.trail.system_id else ''),
         'step_up': f.grade == record.best[f.type] + 1}
        for f in picked[:limit]
    ]
