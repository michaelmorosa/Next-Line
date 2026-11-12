"""Existing features: map old kinds to the new types and number them in the order they were pinned. Every existing
feature becomes a draft, since none has a grade yet; the trail team grades and certifies them.

Riders' old progress becomes logs: a cleaned feature gets one 'cleaned' log per clean (dated the first clean), and
'almost' becomes one 'sketchy' log. The old rows are kept, read-only.
"""
from django.db import migrations

TYPE_MAP = {'gap': 'jump', 'berm': 'corner', 'technical': 'other'}


def forwards(apps, schema_editor):
    Feature = apps.get_model('trails', 'Feature')
    FeatureProgress = apps.get_model('trails', 'FeatureProgress')
    FeatureLog = apps.get_model('trails', 'FeatureLog')

    positions = {}
    for feature in Feature.objects.order_by('trail_id', 'created_at', 'id'):
        positions[feature.trail_id] = positions.get(feature.trail_id, 0) + 1
        feature.type = TYPE_MAP.get(feature.type, feature.type)
        feature.position = positions[feature.trail_id]
        feature.status = 'draft'
        feature.save(update_fields=['type', 'position', 'status'])

    logs = []
    for p in FeatureProgress.objects.all():
        when = p.first_cleaned_at or p.updated_at
        if p.status == 'cleaned':
            for i in range(max(1, p.clean_count)):
                logs.append(FeatureLog(user_id=p.user_id, feature_id=p.feature_id, outcome='cleaned',
                                       ridden_on=when.date(), logged_at=when, note=p.note if i == 0 else ''))
        elif p.status == 'almost':
            logs.append(FeatureLog(user_id=p.user_id, feature_id=p.feature_id, outcome='sketchy',
                                   ridden_on=when.date(), logged_at=when, note=p.note))
    FeatureLog.objects.bulk_create(logs)


def backwards(apps, schema_editor):
    Feature = apps.get_model('trails', 'Feature')
    reverse = {'jump': 'jump', 'corner': 'berm', 'other': 'other'}
    for feature in Feature.objects.all():
        feature.type = reverse.get(feature.type, feature.type)
        feature.save(update_fields=['type'])
    apps.get_model('trails', 'FeatureLog').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('trails', '0006_feature_ladders')]

    operations = [migrations.RunPython(forwards, backwards)]
