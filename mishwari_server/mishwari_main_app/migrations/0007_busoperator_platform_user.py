# Generated migration for adding platform_user field to BusOperator

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def populate_platform_user(apps, schema_editor):
    """Populate platform_user for existing operators"""
    BusOperator = apps.get_model('mishwari_main_app', 'BusOperator')
    Driver = apps.get_model('mishwari_main_app', 'Driver')
    
    for operator in BusOperator.objects.all():
        # Find driver associated with this operator
        driver = Driver.objects.filter(operator=operator).first()
        if driver:
            operator.platform_user = driver.user
            operator.save()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('mishwari_main_app', '0006_remove_citylist_unique_coordinates_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='busoperator',
            name='platform_user',
            field=models.ForeignKey(
                blank=True,
                help_text='Platform user who owns this operator (null for external operators)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='owned_operator',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.RunPython(populate_platform_user, reverse_code=migrations.RunPython.noop),
    ]
