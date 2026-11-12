import mimetypes

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from rides.analysis import haversine
from rides.models import Ride
from trails.serializers import FeatureSerializer, progress_for
from trails.views import features_with_counts

from . import content, services, xp
from .models import Attempt, Challenge, Mastery, PracticeSession, XPEntry
from .serializers import (
    AttemptInputSerializer, AttemptSerializer, MasterInputSerializer, SessionInputSerializer, SessionSerializer,
    XPEntrySerializer,
)
from .services import ProgressionError
from .state import next_up, rider_skills
from .summary import challenge_data, challenge_list

NEARBY_FEATURES = 5
NEARBY_MAX_M = 50_000
HISTORY_SESSIONS = 50
XP_PAGE = 50
SUMMARY_FIELDS = ('id', 'name', 'branch', 'tier', 'prerequisites', 'description', 'tags', 'draft', 'capstone')


def error(exc):
    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def skill_or_404(skill_id):
    skill = content.skills_by_id().get(skill_id)
    if not skill:
        raise Http404
    return skill


def standing(user):
    """Level and practice streak, returned with every change so the app can update its bars."""
    return {'level': xp.level(user), 'streak_weeks': xp.practice_streak(user)}


def outcome(user, result, skill_id):
    """What a practice, attempt or mastery earned, plus where the rider now stands on that skill."""
    return {
        'created': result.get('created', True),
        'awards': XPEntrySerializer(result['awards'], many=True).data,
        'xp_gained': sum(a.amount for a in result['awards']),
        'capped': result.get('capped', False),
        'challenges_completed': [c['entry'].challenge.title for c in result['challenges']],
        'skill': rider_skills(user)[skill_id],
        **standing(user),
    }


@api_view(['GET'])
def skill_tree(request):
    """The whole tree with the rider's state on each skill, where to draw it, and what to work on next."""
    tree = content.skill_tree()
    skills = tree['skills']
    states = rider_skills(request.user, skills)
    depths = content.depths(skills)
    unlocks = content.unlocks(skills)
    return Response({
        'version': tree['version'],
        'branches': tree['branches'],
        'skills': [
            {**{k: s.get(k) for k in SUMMARY_FIELDS}, 'depth': depths[s['id']], 'unlocks': unlocks[s['id']],
             **states[s['id']]}
            for s in skills
        ],
        'next_up': next_up(skills, states),
        'mastered_count': sum(1 for v in states.values() if v['state'] == 'mastered'),
        **standing(request.user),
    })


def rider_location(request):
    try:
        return float(request.query_params['lat']), float(request.query_params['lng'])
    except (KeyError, ValueError):
        pass
    ride = Ride.objects.filter(user=request.user).order_by('-started_at').only('track').first()
    if ride and ride.track:
        return ride.track[0][1], ride.track[0][2]
    return None


def nearby_features(request, skill):
    """Trail features whose type matches the skill's tags, closest first. Empty without a location."""
    kinds = {content.TAG_TYPES[t] for t in skill['tags'] if t in content.TAG_TYPES}
    where = rider_location(request)
    if not kinds or not where:
        return []
    features = list(features_with_counts(request.user).live().filter(type__in=kinds).select_related('trail'))
    near = sorted(
        ((haversine(where[0], where[1], f.lat, f.lng), f) for f in features), key=lambda pair: pair[0],
    )
    near = [(d, f) for d, f in near if d <= NEARBY_MAX_M][:NEARBY_FEATURES]
    found = [f for _, f in near]
    data = FeatureSerializer(found, many=True, context={'progress': progress_for(request.user, found)}).data
    for row, (distance, feature) in zip(data, near):
        row['trail_name'] = feature.trail.name
        row['distance_m'] = round(distance)
    return data


@api_view(['GET'])
def skill_detail(request, skill_id):
    skill = skill_or_404(skill_id)
    by_id = content.skills_by_id()
    user = request.user
    mastery = Mastery.objects.filter(user=user, skill_id=skill_id).first()
    return Response({
        **skill,
        **rider_skills(user)[skill_id],
        'prerequisite_names': {p: by_id[p]['name'] for p in skill['prerequisites']},
        'unlocks': [{'id': s, 'name': by_id[s]['name']} for s in content.unlocks(content.skill_tree()['skills'])[skill_id]],
        'mastery': mastery and {
            'mastered_at': mastery.mastered_at, 'confirmed_test': mastery.confirmed_test,
            'coach_verified': mastery.coach_verified,
        },
        # 'sessions' and 'attempts' (counts) come from rider_skills; these are the rows.
        'history': SessionSerializer(
            PracticeSession.objects.filter(user=user, skill_id=skill_id)[:HISTORY_SESSIONS], many=True,
        ).data,
        'attempt_videos': AttemptSerializer(Attempt.objects.filter(user=user, skill_id=skill_id), many=True).data,
        'nearby_features': nearby_features(request, skill),
        'requirements': content.rules()['mastery'],
    })


@api_view(['POST'])
def log_session(request, skill_id):
    skill_or_404(skill_id)
    data = SessionInputSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    d = data.validated_data
    try:
        result = services.log_session(request.user, skill_id, d['practiced_on'], client_id=d['client_id'],
                                      drill_index=d.get('drill_index'), note=d['note'])
    except ProgressionError as e:
        return error(e)
    body = {'session': SessionSerializer(result['session']).data, **outcome(request.user, result, skill_id)}
    return Response(body, status=status.HTTP_201_CREATED if result['created'] else status.HTTP_200_OK)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def add_attempt(request, skill_id):
    skill_or_404(skill_id)
    data = AttemptInputSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    d = data.validated_data
    try:
        result = services.add_attempt(request.user, skill_id, d['video'], d['practiced_on'],
                                      client_id=d['client_id'], duration_s=d.get('duration_s'), note=d['note'])
    except ProgressionError as e:
        return error(e)
    body = {'attempt': AttemptSerializer(result['attempt']).data, **outcome(request.user, result, skill_id)}
    return Response(body, status=status.HTTP_201_CREATED if result['created'] else status.HTTP_200_OK)


@api_view(['POST'])
@parser_classes([JSONParser])
def master_skill(request, skill_id):
    skill_or_404(skill_id)
    data = MasterInputSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        result = services.master_skill(request.user, skill_id, data.validated_data['confirmed_test'])
    except ProgressionError as e:
        return error(e)
    by_id = content.skills_by_id()
    body = {
        **outcome(request.user, result, skill_id),
        'unlocked': [{'id': s, 'name': by_id[s]['name'], 'tier': by_id[s]['tier']} for s in result['unlocked']],
        'level_before': result['level_before'],
        'leveled_up': result['level_after']['level'] > result['level_before']['level'],
    }
    return Response(body, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def attempt_video(request, attempt_id):
    """The rider's own attempt video. In production nginx sends the file (X-Accel-Redirect) after this check."""
    attempt = get_object_or_404(Attempt, pk=attempt_id, user=request.user)
    content_type = mimetypes.guess_type(attempt.video.name)[0] or 'video/mp4'
    if settings.USE_X_ACCEL_REDIRECT:
        response = HttpResponse(content_type=content_type)
        response['X-Accel-Redirect'] = f'/protected-media/{attempt.video.name}'
        return response
    try:
        return FileResponse(attempt.video.open('rb'), content_type=content_type)
    except FileNotFoundError:
        raise Http404


@api_view(['GET'])
def xp_history(request):
    """The rider's ledger, newest first. ?before=<entry id> for the next page."""
    entries = XPEntry.objects.filter(user=request.user).select_related('challenge')
    before = request.query_params.get('before')
    if before and before.isdigit():
        entries = entries.filter(id__lt=int(before))
    page = list(entries.order_by('-id')[:XP_PAGE + 1])
    return Response({
        'results': XPEntrySerializer(page[:XP_PAGE], many=True).data,
        'next_before': page[XP_PAGE - 1].id if len(page) > XP_PAGE else None,
        **standing(request.user),
    })


@api_view(['GET'])
def challenges(request):
    return Response(challenge_list(request.user))


@api_view(['POST'])
def join_challenge(request, challenge_id):
    challenge = get_object_or_404(Challenge, pk=challenge_id)
    try:
        entry = services.join_challenge(request.user, challenge)
    except ProgressionError as e:
        return error(e)
    return Response(challenge_data(challenge, entry, timezone.localdate()), status=status.HTTP_201_CREATED)
