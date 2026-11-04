from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from progression import ride_xp, xp
from rides.models import Ride


class Command(BaseCommand):
    help = ("Give existing riders the XP their past rides and cleaned features would have earned. "
            "Safe to run again: each ride and feature pays out once.")

    def add_arguments(self, parser):
        parser.add_argument('--user', help='Only this username')

    def handle(self, *args, **options):
        users = get_user_model().objects.order_by('id')
        if options['user']:
            users = users.filter(username=options['user'])
        for user in users:
            awards = []
            # Oldest first, so "biggest air yet" and "first clean climb" mean the same as they did live.
            for ride in Ride.objects.filter(user=user).order_by('started_at', 'id'):
                awards += ride_xp.award_ride(ride)
            awards += ride_xp.award_features(user)
            level = xp.level(user)
            self.stdout.write(f"{user.username}: +{sum(a.amount for a in awards)} XP, now level {level['level']} "
                              f"({level['title']}, {level['total']} XP)")
