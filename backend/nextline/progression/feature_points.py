"""Points for riding features, from rider logs. Every value is in content/rules.json ("xp" section).

- First clean of a feature: first_clean_per_grade x grade.
- Each later clean: repeat_clean, at most caps.repeat_cleans_per_feature_per_week per feature per week (ISO weeks
  of the rider's local ride date).
- "Rode it, sketchy": sketchy_per_grade x grade, once per feature.
- "Walked it": `walked` (0), and it's still logged.
- Cleaning every certified feature on a trail, or every one of a type in a trail system (a ladder), pays a bonus
  once, when there are at least bonuses.min_features of them.

Grades come from the log (grade_at_log), so regrading a feature doesn't change what was earned. Only live
features pay; logs on a draft pay when it's certified (catch_up). Deleting a log adds corrections, never edits.
"""
from django.db.models import Q, Sum

from trails.models import Certification, Feature, FeatureLog, Outcome
from trails.progress import cleaned_ids

from . import content, xp
from .models import Reason, XPEntry


def _entries(user, prefix):
    return XPEntry.objects.filter(user=user).filter(
        Q(source__startswith=prefix) | Q(source__startswith='undo:' + prefix)
    )


def net(user, prefix):
    """Points still standing from sources starting with `prefix`, after corrections."""
    return _entries(user, prefix).aggregate(t=Sum('amount'))['t'] or 0


def net_count(user, prefix):
    """How many awards with this prefix still stand: awards minus their corrections."""
    paid = XPEntry.objects.filter(user=user, source__startswith=prefix).count()
    undone = XPEntry.objects.filter(user=user, source__startswith='undo:' + prefix).count()
    return paid - undone


def first_clean_paid(user, feature_id):
    # 'feature:<id>' is how the ledger recorded first cleans before grades.
    return net(user, f'first_clean:{feature_id}:') + net(user, f'feature:{feature_id}') > 0


def _grade(log):
    return log.grade_at_log or log.feature.grade


def award_log(log):
    """Points for one log. Safe to call again: a log that has already paid out earns nothing more."""
    feature = log.feature
    grade = _grade(log)
    if not feature.is_live or not grade:
        return []
    if XPEntry.objects.filter(user=log.user, log_id=log.id).exclude(reason=Reason.CORRECTION).exists():
        return []
    values, caps = content.rules()['xp'], content.rules()['caps']
    user, f, at = log.user, feature.id, log.logged_at
    ids = {'feature_id': f, 'log_id': log.id, 'at': at}
    awards = []
    if log.outcome == Outcome.CLEANED:
        if not first_clean_paid(user, f):
            awards.append(xp.award(user, Reason.FIRST_CLEAN, f'first_clean:{f}:{log.id}',
                                   values['first_clean_per_grade'] * grade, **ids))
        else:
            prefix = f'repeat:{f}:{xp.week_key(log.ridden_on)}:'
            if net_count(user, prefix) < caps['repeat_cleans_per_feature_per_week']:
                awards.append(xp.award(user, Reason.REPEAT_CLEAN, prefix + str(log.id), values['repeat_clean'], **ids))
        awards += award_bonuses(user, feature, at, log_id=log.id)
    elif log.outcome == Outcome.SKETCHY:
        if net(user, f'sketchy:{f}:') <= 0:
            awards.append(xp.award(user, Reason.SKETCHY, f'sketchy:{f}:{log.id}',
                                   values['sketchy_per_grade'] * grade, **ids))
    elif values['walked']:
        awards.append(xp.award(user, Reason.SKETCHY, f'walked:{f}:{log.id}', values['walked'], **ids))
    return [a for a in awards if a]


def award_bonuses(user, feature, at=None, log_id=None):
    """Trail and ladder bonuses the rider has just completed. Each pays once, ever."""
    values, minimum = content.rules()['xp'], content.rules()['bonuses']['min_features']
    cleaned = cleaned_ids(user)
    certified = Feature.objects.filter(status=Certification.CERTIFIED, trail__owner__isnull=True)
    awards = []
    on_trail = set(certified.filter(trail=feature.trail_id).values_list('id', flat=True))
    if len(on_trail) >= minimum and on_trail <= cleaned:
        awards.append(xp.award(user, Reason.TRAIL_COMPLETE, f'trail_complete:{feature.trail_id}',
                               values['trail_complete'], at=at, log_id=log_id))
    system_id = feature.trail.system_id
    if system_id:
        ladder = set(certified.filter(trail__system=system_id, type=feature.type).values_list('id', flat=True))
        if len(ladder) >= minimum and ladder <= cleaned:
            awards.append(xp.award(user, Reason.LADDER_COMPLETE, f'ladder_complete:{system_id}:{feature.type}',
                                   values['ladder_complete'], at=at, log_id=log_id))
    return [a for a in awards if a]


def undo_log(log):
    """Corrections for what a log earned, before it's deleted. If it was the first clean and the rider has other
    cleans of the feature, the earliest of those becomes the first clean."""
    entries = list(XPEntry.objects.filter(user=log.user, log_id=log.id).exclude(reason=Reason.CORRECTION))
    corrections = [_correct(e) for e in entries]
    was_first = any(e.reason == Reason.FIRST_CLEAN for e in entries)
    if was_first:
        next_first = (
            FeatureLog.objects.filter(user=log.user, feature=log.feature, outcome=Outcome.CLEANED)
            .exclude(pk=log.pk).order_by('ridden_on', 'logged_at', 'id').first()
        )
        if next_first and log.feature.is_live and _grade(next_first):
            for e in XPEntry.objects.filter(user=log.user, log_id=next_first.id, reason=Reason.REPEAT_CLEAN):
                corrections.append(_correct(e))
            corrections.append(xp.award(
                log.user, Reason.FIRST_CLEAN, f'first_clean:{log.feature_id}:{next_first.id}',
                content.rules()['xp']['first_clean_per_grade'] * _grade(next_first),
                feature_id=log.feature_id, log_id=next_first.id, at=next_first.logged_at,
            ))
    return [c for c in corrections if c]


def _correct(entry):
    return xp.award(entry.user, Reason.CORRECTION, f'undo:{entry.source}', -entry.amount,
                    feature_id=entry.feature_id, log_id=entry.log_id)


def delete_log(log):
    """Delete a rider's log, correcting its points first."""
    undo_log(log)
    log.delete()


def catch_up(user):
    """First cleans and sketchy rides on features that were drafts when logged and are live now."""
    awards = []
    logs = (
        FeatureLog.objects.filter(user=user, feature__in=Feature.objects.live(),
                                  outcome__in=(Outcome.CLEANED, Outcome.SKETCHY))
        .select_related('feature__trail').order_by('ridden_on', 'logged_at', 'id')
    )
    done = set()
    for log in logs:
        key = (log.feature_id, log.outcome)
        if key in done:
            continue
        done.add(key)
        if log.outcome == Outcome.CLEANED and first_clean_paid(user, log.feature_id):
            continue
        if log.outcome == Outcome.SKETCHY and net(user, f'sketchy:{log.feature_id}:') > 0:
            continue
        awards += award_log(log)
    return awards


def points_for_logs(user, logs):
    """Ledger entries (including corrections) belonging to these logs."""
    return XPEntry.objects.filter(user=user, log_id__in=[log.id for log in logs])
