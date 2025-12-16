# Generated migration for adding index on Trip.status

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mishwari_main_app', '0017_update_role_choices'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trip',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('published', 'Published'),
                    ('active', 'Active'),
                    ('completed', 'Completed'),
                    ('cancelled', 'Cancelled')
                ],
                db_index=True,
                default='draft',
                max_length=20
            ),
        ),
    ]
