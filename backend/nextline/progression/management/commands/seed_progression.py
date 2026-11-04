from django.core.management.base import BaseCommand

from progression.services import seed_challenges


class Command(BaseCommand):
    help = 'Create or update challenges from progression/content/challenges.json.'

    def handle(self, *args, **options):
        for challenge in seed_challenges():
            self.stdout.write(f'{challenge.title}: {challenge.starts_on} to {challenge.ends_on}')
