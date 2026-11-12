from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('trails', '0004_feature_approved')]

    operations = [migrations.RenameField('feature', 'kind', 'type')]
