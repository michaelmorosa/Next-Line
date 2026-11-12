from django.apps import AppConfig
from django.db.models.signals import post_migrate

TRAIL_TEAM_GROUP = 'Trail team'
TRAIL_TEAM_PERMISSIONS = (
    'edit_feature', 'certify_feature',
    'add_feature', 'change_feature', 'view_feature',
    'add_featuremedia', 'change_featuremedia', 'delete_featuremedia', 'view_featuremedia',
    'change_featurereport', 'view_featurereport',
    'change_gradingguidelines', 'view_gradingguidelines',
    'view_trail', 'change_trail', 'view_trailsystem',
)


def ensure_trail_team(sender, **kwargs):
    """The Trail team group, with what the team needs to add, grade and certify features. Add people to it in the
    admin (Users → a user → Groups) and give them staff status to use the admin from a computer."""
    from django.contrib.auth.models import Group, Permission

    group, _ = Group.objects.get_or_create(name=TRAIL_TEAM_GROUP)
    perms = Permission.objects.filter(content_type__app_label='trails', codename__in=TRAIL_TEAM_PERMISSIONS)
    group.permissions.add(*perms)


class TrailsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trails'

    def ready(self):
        post_migrate.connect(ensure_trail_team, sender=self)
