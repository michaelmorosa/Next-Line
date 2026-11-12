"""What happens when a rider practises, uploads an attempt, masters a skill or joins a challenge."""
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import content, xp
from .models import Attempt, Challenge, ChallengeEntry, GoalType, Mastery, PracticeSession, Reason
from .state import IN_PROGRESS, can_practice, newly_ready, rider_skills

# How far the app's local date may be from the server's UTC date (time zones span about ±14 hours).
LOCAL_DATE_SLACK = timedelta(days=1)


class ProgressionError(Exception):
    """A request the rules don't allow. The message is shown to the rider."""


def get_skill(skill_id):
    skill = content.skills_by_id().get(skill_id)
    if not skill:
        raise ProgressionError('Unknown skill.')
    return skill


def check_local_date(practiced_on, today=None):
    today = today or timezone.now().date()
    if abs(practiced_on - today) > LOCAL_DATE_SLACK:
        raise ProgressionError("Practice can only be logged for today.")


def require_practicable(user, skill):
    if not can_practice(rider_skills(user)[skill['id']]['state']):
        names = content.skills_by_id()
        needs = ', '.join(names[p]['name'] for p in skill['prerequisites'])
        raise ProgressionError(f"{skill['name']} is locked. Master {needs} first.")


def log_session(user, skill_id, practiced_on, *, client_id=None, drill_index=None, note='', ride=None, today=None,
                at=None):
    """Save a drill session and award what it earned. Returns {session, created, awards, capped, challenges}.

    `at` backdates it (the demo rider); the API always logs now.
    """
    skill = get_skill(skill_id)
    check_local_date(practiced_on, today)
    if drill_index is not None and not 0 <= drill_index < len(skill['drills']):
        raise ProgressionError('Unknown drill.')
    if client_id:
        existing = PracticeSession.objects.filter(user=user, client_id=client_id).first()
        if existing:
            return {'session': existing, 'created': False, 'awards': [], 'capped': False, 'challenges': []}
    require_practicable(user, skill)
    extra = {'client_id': client_id} if client_id else {}
    with transaction.atomic():
        session = PracticeSession.objects.create(
            user=user, skill_id=skill_id, practiced_on=practiced_on, drill_index=drill_index, note=note, ride=ride,
            logged_at=at or timezone.now(), **extra,
        )
        earned = xp.award_session(session)
        awards = [a for a in (earned, xp.award_streak(user, practiced_on, at)) if a]
        completed = check_challenges(user, at)
    awards += [c['award'] for c in completed if c['award']]
    return {'session': session, 'created': True, 'awards': awards, 'capped': earned is None, 'challenges': completed}


def add_attempt(user, skill_id, video, practiced_on, *, client_id=None, duration_s=None, note='', today=None,
                at=None):
    """Save an attempt video and award what it earned. Same shape as log_session, with 'attempt'."""
    skill = get_skill(skill_id)
    check_local_date(practiced_on, today)
    max_s = content.rules()['attempts']['max_seconds']
    if duration_s is not None and duration_s > max_s + 1:
        raise ProgressionError(f'Attempt videos can be up to {max_s} seconds.')
    if client_id:
        existing = Attempt.objects.filter(user=user, client_id=client_id).first()
        if existing:
            return {'attempt': existing, 'created': False, 'awards': [], 'capped': False, 'challenges': []}
    require_practicable(user, skill)
    extra = {'client_id': client_id} if client_id else {}
    with transaction.atomic():
        attempt = Attempt(user=user, skill_id=skill_id, practiced_on=practiced_on, duration_s=duration_s, note=note,
                          created_at=at or timezone.now(), **extra)
        attempt.video.save(getattr(video, 'name', 'attempt.mp4'), video, save=False)
        attempt.save()
        earned = xp.award_attempt(attempt)
        awards = [a for a in (earned, xp.award_streak(user, practiced_on, at)) if a]
        completed = check_challenges(user, at)
    awards += [c['award'] for c in completed if c['award']]
    return {'attempt': attempt, 'created': True, 'awards': awards, 'capped': earned is None, 'challenges': completed}


def master_skill(user, skill_id, confirmed_test, at=None):
    """Record a mastery once the requirements are met and the rider confirms the test.

    Returns {mastery, awards, unlocked (skill ids that just became ready), level_before, level_after, challenges}.
    """
    skill = get_skill(skill_id)
    rules = content.rules()
    states = rider_skills(user)
    info = states[skill_id]
    if info['state'] == 'mastered':
        raise ProgressionError(f"You've already mastered {skill['name']}.")
    if info['state'] != IN_PROGRESS or info['missing']:
        needs = ', '.join(info['missing']) or 'some practice first'
        raise ProgressionError(f"Not yet: {skill['name']} needs {needs}.")
    if rules['mastery']['requires_confirmation'] and not confirmed_test:
        raise ProgressionError('Confirm you passed the mastery test.')

    level_before = xp.level(user)
    mastered_before = {sid for sid, s in states.items() if s['state'] == 'mastered'}
    try:
        with transaction.atomic():
            mastery = Mastery.objects.create(user=user, skill_id=skill_id, confirmed_test=bool(confirmed_test),
                                             mastered_at=at or timezone.now())
            earned = xp.award(user, Reason.MASTERY, f'mastery:{skill_id}',
                              rules['xp']['mastery_per_tier'] * skill['tier'], skill_id=skill_id, at=at)
            completed = check_challenges(user, at)
    except IntegrityError:
        raise ProgressionError(f"You've already mastered {skill['name']}.")
    awards = [a for a in [earned] + [c['award'] for c in completed] if a]
    skills = content.skill_tree()['skills']
    return {
        'mastery': mastery,
        'awards': awards,
        'unlocked': newly_ready(skills, mastered_before, mastered_before | {skill_id}),
        'level_before': level_before,
        'level_after': xp.level(user),
        'challenges': completed,
    }


# Challenges.

def is_open(challenge, today=None):
    today = today or timezone.localdate()
    return challenge.starts_on <= today <= challenge.ends_on


def join_challenge(user, challenge, today=None):
    if not is_open(challenge, today):
        raise ProgressionError("This challenge isn't running right now.")
    entry, _ = ChallengeEntry.objects.get_or_create(user=user, challenge=challenge)
    return entry


def challenge_features(challenge):
    """The certified features a 'features' goal covers."""
    from trails.models import Certification, Feature

    features = Feature.objects.filter(status=Certification.CERTIFIED, trail__owner__isnull=True, grade__isnull=False)
    if challenge.system_id:
        features = features.filter(trail__system=challenge.system_id)
    if challenge.feature_type:
        features = features.filter(type=challenge.feature_type)
    if challenge.grade_min:
        features = features.filter(grade__gte=challenge.grade_min)
    if challenge.grade_max:
        features = features.filter(grade__lte=challenge.grade_max)
    return features


def challenge_goal(challenge):
    if challenge.goal_type == GoalType.FEATURES:
        return max(1, challenge_features(challenge).count())
    return challenge.goal_count


def challenge_progress(entry):
    """How far the rider is toward the goal. Only counts what happened after joining and inside the dates."""
    from django.db.models import Min

    from trails.models import FeatureLog, Outcome

    challenge = entry.challenge
    if challenge.goal_type in (GoalType.NEXT_FEATURES, GoalType.FEATURES):
        cleans = FeatureLog.objects.filter(user=entry.user, outcome=Outcome.CLEANED)
        in_window = cleans.filter(
            logged_at__gte=entry.joined_at, ridden_on__gte=challenge.starts_on, ridden_on__lte=challenge.ends_on,
        )
        if challenge.goal_type == GoalType.FEATURES:
            return in_window.filter(feature__in=challenge_features(challenge)).values('feature').distinct().count()
        # Next features: ones whose first clean ever came during the challenge.
        firsts = cleans.values('feature').annotate(first=Min('logged_at'))
        new = {row['feature'] for row in firsts if row['first'] >= entry.joined_at}
        return in_window.filter(feature__in=new).values('feature').distinct().count()
    if challenge.goal_type == GoalType.SESSIONS:
        return PracticeSession.objects.filter(
            user=entry.user, skill_id__in=challenge.skill_ids, logged_at__gte=entry.joined_at,
            practiced_on__gte=challenge.starts_on, practiced_on__lte=challenge.ends_on,
        ).count()
    return Mastery.objects.filter(
        user=entry.user, skill_id__in=challenge.skill_ids, mastered_at__gte=entry.joined_at,
        mastered_at__date__gte=challenge.starts_on, mastered_at__date__lte=challenge.ends_on,
    ).count()


def check_challenges(user, at=None):
    """Complete any joined challenge whose goal is now met. Returns [{entry, award}] for the ones just completed."""
    done = []
    for entry in ChallengeEntry.objects.filter(user=user, completed_at__isnull=True).select_related('challenge'):
        if challenge_progress(entry) < challenge_goal(entry.challenge):
            continue
        entry.completed_at = at or timezone.now()
        entry.save(update_fields=['completed_at'])
        earned = xp.award(user, Reason.CHALLENGE, f'challenge:{entry.challenge_id}',
                          content.rules()['xp']['challenge_complete'], challenge=entry.challenge, at=at)
        done.append({'entry': entry, 'award': earned})
    return done


def seed_challenges(today=None):
    """Create or update challenges from content/challenges.json. A challenge with no start date starts today."""
    today = today or timezone.localdate()
    out = []
    for c in content.read('challenges.json')['challenges']:
        existing = Challenge.objects.filter(slug=c['slug']).first()
        starts = (
            date.fromisoformat(c['starts_on']) if c.get('starts_on')
            else existing.starts_on if existing else today
        )
        system = None
        if c.get('system'):
            from trails.models import TrailSystem
            system = TrailSystem.objects.filter(slug=c['system']).first()
        challenge, _ = Challenge.objects.update_or_create(slug=c['slug'], defaults={
            'title': c['title'], 'description': c.get('description', ''), 'skill_ids': c.get('skills', []),
            'goal_type': c['goal_type'], 'goal_count': c['goal_count'], 'starts_on': starts,
            'ends_on': starts + timedelta(days=c['days'] - 1), 'system': system,
            'feature_type': c.get('feature_type', ''), 'grade_min': c.get('grade_min'), 'grade_max': c.get('grade_max'),
        })
        out.append(challenge)
    return out
