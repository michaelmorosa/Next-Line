"""A rider's standing on features, derived from their logs. Nothing here is stored."""
from dataclasses import dataclass
from datetime import date, datetime

from .models import FeatureLog, Outcome


@dataclass
class FeatureState:
    cleans: int = 0
    sketchy: int = 0
    walked: int = 0
    first_cleaned_at: datetime | None = None
    first_cleaned_on: date | None = None
    last_outcome: str | None = None
    last_ridden_on: date | None = None

    @property
    def status(self):
        """Best outcome so far: cleaned, sketchy, walked, or not_yet."""
        if self.cleans:
            return Outcome.CLEANED.value
        if self.sketchy:
            return Outcome.SKETCHY.value
        if self.walked:
            return Outcome.WALKED.value
        return 'not_yet'

    @property
    def legacy_status(self):
        """The pre-log status the older app screens understand: locked, almost or cleaned."""
        return {'cleaned': 'cleaned', 'sketchy': 'almost'}.get(self.status, 'locked')


def states(user, features=None, until=None):
    """{feature_id: FeatureState} for every feature the rider has logged (optionally only `features`)."""
    logs = FeatureLog.objects.filter(user=user)
    if features is not None:
        logs = logs.filter(feature__in=features)
    if until is not None:
        logs = logs.filter(logged_at__lte=until)
    out = {}
    for log in logs.order_by('ridden_on', 'logged_at', 'id').only(
        'feature_id', 'outcome', 'ridden_on', 'logged_at',
    ):
        s = out.setdefault(log.feature_id, FeatureState())
        if log.outcome == Outcome.CLEANED:
            s.cleans += 1
            if s.first_cleaned_at is None:
                s.first_cleaned_at, s.first_cleaned_on = log.logged_at, log.ridden_on
        elif log.outcome == Outcome.SKETCHY:
            s.sketchy += 1
        else:
            s.walked += 1
        s.last_outcome, s.last_ridden_on = log.outcome, log.ridden_on
    return out


def cleaned_ids(user, until=None):
    """Ids of features the rider has cleaned at least once."""
    logs = FeatureLog.objects.filter(user=user, outcome=Outcome.CLEANED)
    if until is not None:
        logs = logs.filter(logged_at__lte=until)
    return set(logs.values_list('feature_id', flat=True))
