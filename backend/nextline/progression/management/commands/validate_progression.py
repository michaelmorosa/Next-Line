from django.core.management.base import BaseCommand, CommandError

from progression.content import CONTENT_DIR, validate


class Command(BaseCommand):
    help = 'Check the skill tree, point rules and challenges in progression/content/ for mistakes.'

    def add_arguments(self, parser):
        parser.add_argument('--dir', help=f'Folder holding the content files (default {CONTENT_DIR})')

    def handle(self, *args, **options):
        errors, warnings = validate(options['dir'])
        for w in warnings:
            self.stdout.write(self.style.WARNING(f'warning: {w}'))
        for e in errors:
            self.stderr.write(self.style.ERROR(f'error: {e}'))
        if errors:
            raise CommandError(f'{len(errors)} error(s) in progression content.')
        self.stdout.write(self.style.SUCCESS('Progression content is valid.'))
