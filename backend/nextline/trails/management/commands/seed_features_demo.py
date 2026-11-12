"""Demo data for trying the app: a made-up trail system (Cedar Hollow) with 3 trails and 31 graded features with
placeholder photos, two demo trail-team members, and a demo rider with eight weeks of history.

    python manage.py seed_features_demo                 # create, or recreate from scratch
    python manage.py seed_features_demo --remove        # remove every bit of it

Everything it makes is marked: the trail system has is_demo set, and the users are the DEMO_TEAM usernames plus the
rider's. Removing deletes those trails, features, photo files, logs, points and users, and nothing else.
"""
import io
import math
import secrets
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from progression import feature_points, xp
from trails.apps import TRAIL_TEAM_GROUP
from trails.models import Feature, FeatureLog, FeatureMedia, Trail, TrailSystem
from trails.share import display, semibold
from trails.skills import safety

DEMO_SLUG = 'demo-cedar-hollow'
DEMO_TEAM = ('demo_team_ana', 'demo_team_ben')
ORIGIN = (45.381, -121.702)  # trailhead of the made-up system

# (name, difficulty, length m, drop m, bearing in degrees)
TRAILS = [
    ('Fern Gully', 'green', 1600, 140, 120),
    ('Switchback Alley', 'blue', 2100, 260, 200),
    ('The Chute', 'black', 1200, 230, 160),
]

# trail index, name, type, grade, extras. Listed in riding order per trail.
FEATURES = [
    (0, 'Root Step', 'drop', 1, {'drop_height_m': 0.25, 'how_to_ride': 'Roll it in attack position, weight back a touch.'}),
    (0, 'First Roller', 'jump', 1, {'how_to_ride': 'Pump the back side for free speed. No need to leave the ground.'}),
    (0, 'Mossy Bend', 'corner', 1, {'how_to_ride': 'Brake before it, look through it, outside pedal down.'}),
    (0, 'Fern Roots', 'roots', 1, {'how_to_ride': 'Light hands, let the bike move under you.'}),
    (0, 'Little Ledge', 'drop', 2, {'drop_height_m': 0.4, 'how_to_ride': 'A little speed and lift the front as you reach the lip.'}),
    (0, 'Pump Bump', 'jump', 2, {'gap_length_m': 1.5}),
    (0, 'Bench Berm', 'corner', 2, {'how_to_ride': 'Stay high on the entry, then lean the bike into the wall.'}),
    (0, 'Creek Rocks', 'rock_garden', 1, {'status': 'changed', 'what_can_go_wrong': 'Wet rocks are slick; walk it after rain.'}),
    (0, 'Log Skinny', 'skinny', 1, {'how_to_ride': 'Eyes on the far end of the log, not your front wheel.'}),
    (0, 'Gully Climb', 'climb', 1, {}),
    (1, 'Granite Roll', 'drop', 3, {'drop_height_m': 0.6, 'has_ride_around': True, 'ride_around_grade': 1,
                                    'ride_around_note': 'Trail to the left of the slab.',
                                    'how_to_ride': 'Roll it slow, heels down, hips back as the front drops.'}),
    (1, 'Twin Tables', 'jump', 3, {'gap_length_m': 2.5, 'how_to_ride': 'Same speed as the berm before it. Soak the lip.'}),
    (1, 'Switchback One', 'corner', 3, {}),
    (1, 'Root Web', 'roots', 2, {}),
    (1, 'Rattle Garden', 'rock_garden', 2, {'how_to_ride': 'Pick the line before you drop in; stay off the brakes in it.'}),
    (1, 'The Slab', 'steep', 2, {'steepness_deg': 18}),
    (1, 'Kicker Table', 'jump', 4, {'gap_length_m': 3.5}),
    (1, 'Switchback Two', 'corner', 4, {'what_can_go_wrong': 'Overshooting into the trees on the outside.'}),
    (1, 'Boulder Drop', 'drop', 4, {'drop_height_m': 0.85, 'has_ride_around': True, 'ride_around_grade': 2,
                                    'ride_around_note': 'Roll down the gully to the right.'}),
    (1, 'Plank Bridge', 'skinny', 2, {'stale': True}),
    (1, 'Tech Climb', 'climb', 2, {}),
    (2, 'Chute Entry', 'steep', 3, {'steepness_deg': 24}),
    (2, 'Chunk Run', 'rock_garden', 3, {}),
    (2, 'Big Step', 'drop', 5, {'drop_height_m': 1.1, 'has_ride_around': True, 'ride_around_grade': 2,
                                'what_can_go_wrong': 'Not enough speed casing the landing.'}),
    (2, 'Hollow Gap', 'jump', 5, {'gap_length_m': 3.0}),
    (2, 'Off-camber Exit', 'corner', 5, {}),
    (2, 'Wet Roots', 'roots', 3, {}),
    (2, 'Ledge Climb', 'climb', 3, {}),
    (2, 'Steep Roll', 'steep', 4, {'steepness_deg': 28, 'has_ride_around': True, 'ride_around_grade': 3}),
    (2, 'Rock Finale', 'rock_garden', 4, {}),
    (2, 'The Huck', 'drop', 8, {'drop_height_m': 2.2, 'has_ride_around': True, 'ride_around_grade': 3,
                                'what_can_go_wrong': 'Everything. Coaching first.'}),
]

TYPE_COLORS = {
    'drop': (140, 70, 60), 'jump': (150, 100, 50), 'corner': (60, 100, 130), 'rock_garden': (100, 90, 120),
    'roots': (90, 110, 60), 'steep': (130, 80, 100), 'skinny': (70, 110, 100), 'climb': (110, 130, 60),
    'other': (90, 90, 90),
}

# The demo rider's history: (weeks ago, weekday, feature name, outcome). Applied oldest first.
HISTORY = [
    (8, 5, 'Root Step', 'cleaned'), (8, 5, 'First Roller', 'cleaned'), (8, 5, 'Mossy Bend', 'sketchy'),
    (8, 5, 'Fern Roots', 'cleaned'), (8, 5, 'Little Ledge', 'walked'), (8, 5, 'Log Skinny', 'walked'),
    (7, 5, 'Root Step', 'cleaned'), (7, 5, 'First Roller', 'cleaned'), (7, 5, 'Mossy Bend', 'cleaned'),
    (7, 5, 'Fern Roots', 'cleaned'), (7, 5, 'Gully Climb', 'cleaned'), (7, 5, 'Log Skinny', 'sketchy'),
    (6, 2, 'Mossy Bend', 'cleaned'), (6, 2, 'Little Ledge', 'sketchy'), (6, 2, 'Pump Bump', 'cleaned'),
    (6, 2, 'Log Skinny', 'cleaned'), (6, 2, 'Gully Climb', 'cleaned'),
    (5, 6, 'Little Ledge', 'cleaned'), (5, 6, 'Pump Bump', 'cleaned'), (5, 6, 'Bench Berm', 'sketchy'),
    (5, 6, 'Log Skinny', 'cleaned'), (5, 6, 'Root Step', 'cleaned'),
    (4, 5, 'Little Ledge', 'cleaned'), (4, 5, 'Bench Berm', 'cleaned'), (4, 5, 'Root Web', 'cleaned'),
    (4, 5, 'The Slab', 'cleaned'), (4, 5, 'Rattle Garden', 'sketchy'), (4, 5, 'Plank Bridge', 'walked'),
    (3, 6, 'Bench Berm', 'cleaned'), (3, 6, 'The Slab', 'cleaned'), (3, 6, 'Rattle Garden', 'cleaned'),
    (3, 6, 'Twin Tables', 'walked'), (3, 6, 'Tech Climb', 'sketchy'), (3, 6, 'Granite Roll', 'walked'),
    (2, 5, 'Switchback One', 'sketchy'), (2, 5, 'Root Web', 'cleaned'), (2, 5, 'Rattle Garden', 'cleaned'),
    (2, 5, 'Granite Roll', 'sketchy'), (2, 5, 'Twin Tables', 'sketchy'), (2, 5, 'Fern Roots', 'cleaned'),
    (1, 6, 'Granite Roll', 'cleaned'), (1, 6, 'Switchback One', 'cleaned'), (1, 6, 'Twin Tables', 'cleaned'),
    (1, 6, 'Boulder Drop', 'walked'), (1, 6, 'Chute Entry', 'walked'), (1, 6, 'Pump Bump', 'cleaned'),
    (0, 1, 'Switchback One', 'cleaned'), (0, 1, 'Granite Roll', 'cleaned'),
]


def trail_path(start, length_m, bearing, points=40):
    """A wiggly line `length_m` long heading roughly along `bearing` from `start`."""
    lat, lng = start
    step = length_m / points
    path = [[lat, lng]]
    for i in range(points):
        b = math.radians(bearing + 35 * math.sin(i / 3))
        lat += step * math.cos(b) / 111_320
        lng += step * math.sin(b) / (111_320 * math.cos(math.radians(lat)))
        path.append([round(lat, 6), round(lng, 6)])
    return path


def placeholder_photo(name, type_, kind):
    """A clearly fake photo: the type's colour, the feature's name and DEMO across it."""
    base = TYPE_COLORS.get(type_, (90, 90, 90))
    image = Image.new('RGB', (1600, 1200), base)
    draw = ImageDraw.Draw(image)
    for y in range(1200):  # light at the top, like sky over trail
        k = y / 1200
        draw.line([(0, y), (1600, y)], fill=tuple(int(c * (0.7 + 0.5 * (1 - k))) for c in base))
    draw.polygon([(0, 900), (1600, 650), (1600, 1200), (0, 1200)], fill=tuple(int(c * 0.55) for c in base))
    draw.text((800, 480), 'DEMO', font=display(260), fill=(255, 255, 255), anchor='mm')
    draw.text((800, 680), name.upper(), font=semibold(72), fill=(255, 255, 255), anchor='mm')
    draw.text((800, 780), f'{kind} photo · placeholder', font=semibold(40), fill=(235, 235, 235), anchor='mm')
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=80)
    return ContentFile(out.getvalue(), name='photo.jpg')


def remove_demo(rider_username):
    """Delete everything the demo made. Returns how many features went."""
    User = get_user_model()
    trails = Trail.objects.filter(system__is_demo=True, owner__isnull=True)
    features = Feature.objects.filter(trail__in=trails)
    count = features.count()
    for media in FeatureMedia.objects.filter(feature__in=features):
        media.file.delete(save=False)
        media.thumbnail.delete(save=False)
    trails.delete()  # features, media rows and logs go with them
    TrailSystem.objects.filter(is_demo=True).delete()
    User.objects.filter(username__in=(*DEMO_TEAM, rider_username)).delete()  # their logs and points go too
    return count


class Command(BaseCommand):
    help = 'Create (or recreate) the Cedar Hollow demo trail system and a demo rider. --remove deletes it all.'

    def add_arguments(self, parser):
        parser.add_argument('--remove', action='store_true', help='Remove the demo data and stop')
        parser.add_argument('--username', default='demo', help='The demo rider (default: demo)')
        parser.add_argument('--password', help='The demo rider\'s password. Default: a random one, printed at the end')

    def handle(self, *args, **options):
        username = options['username']
        with transaction.atomic():
            removed = remove_demo(username)
        if options['remove']:
            self.stdout.write(self.style.SUCCESS(f'Removed the demo: {removed} features and the demo users.'))
            return

        User = get_user_model()
        now = timezone.now()
        password = options['password'] or secrets.token_urlsafe(9)
        with transaction.atomic():
            team = Group.objects.get(name=TRAIL_TEAM_GROUP)
            ana, ben = (User.objects.create_user(username=u, email=f'{u}@demo.nextline.invalid') for u in DEMO_TEAM)
            for member in (ana, ben):
                member.set_unusable_password()
                member.save()
                member.groups.add(team)

            system = TrailSystem.objects.create(
                name='Cedar Hollow (demo)', slug=DEMO_SLUG, location='Made-up demo area', is_demo=True,
                lat=ORIGIN[0], lng=ORIGIN[1],
                description='A made-up trail system for trying Next Line. The trails, features and photos are '
                            'placeholders. Remove it with `manage.py seed_features_demo --remove`.',
            )
            trails = []
            for i, (name, difficulty, length, drop, bearing) in enumerate(TRAILS):
                start = (ORIGIN[0] - 0.002 * i, ORIGIN[1] + 0.003 * i)
                path = trail_path(start, length, bearing)
                trails.append(Trail.objects.create(
                    name=name, system=system, difficulty=difficulty, length_m=length, drop_m=drop, path=path,
                    start_lat=path[0][0], start_lng=path[0][1], end_lat=path[-1][0], end_lng=path[-1][1],
                ))

            features = {}
            positions = {}
            for trail_index, name, type_, grade, extra in FEATURES:
                trail = trails[trail_index]
                extra = dict(extra)
                stale = extra.pop('stale', False)
                status = extra.pop('status', 'certified')
                positions[trail_index] = positions.get(trail_index, 0) + 1
                point = trail.path[min(len(trail.path) - 1, 3 + positions[trail_index] * 3)]
                verified = now - (timedelta(days=430) if stale else timedelta(days=20))
                feature = Feature.objects.create(
                    trail=trail, name=name, type=type_, grade=grade, lat=point[0], lng=point[1],
                    position=positions[trail_index], status=status, created_by=ana, submitted_by=ana,
                    submitted_at=verified, certified_by=ben, certified_at=verified, last_verified_at=verified,
                    description=f'A demo {type_.replace("_", " ")} on {trail.name}.', **extra,
                )
                for kind in ('feature', 'approach') if positions[trail_index] % 2 else ('feature',):
                    media = FeatureMedia(feature=feature, kind=kind, uploaded_by=ana, position=0 if kind == 'feature' else 1)
                    media.file.save('photo.jpg', placeholder_photo(name, type_, kind), save=False)
                    media.save()
                features[name] = feature

            rider = User.objects.create_user(username=username, email=f'{username}@demo.nextline.invalid',
                                             password=password)
            rider.safety_version = safety()['version']
            rider.safety_accepted_at = now
            rider.save()
            this_monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
            for n, (weeks_ago, weekday, name, outcome) in enumerate(HISTORY):
                day = min(this_monday - timedelta(weeks=weeks_ago) + timedelta(days=weekday), timezone.localdate())
                at = timezone.make_aware(datetime.combine(day, time(10))) + timedelta(minutes=n)
                feature = features[name]
                log = FeatureLog.objects.create(user=rider, feature=feature, outcome=outcome, ridden_on=day,
                                                logged_at=at, grade_at_log=feature.grade)
                feature_points.log_created(log)

        level = xp.level(rider)
        self.stdout.write(self.style.SUCCESS(
            f'Demo ready: {system.name} with {len(trails)} trails and {len(features)} features. '
            f'Demo rider: {username} / {password} (level {level["level"]}, {level["title"]}, '
            f'{level["total"]:,} points). Remove it all with: manage.py seed_features_demo --remove'
        ))
