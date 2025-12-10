from django.db import migrations


def migrate_roles(apps, schema_editor):
    Profile = apps.get_model('mishwari_main_app', 'Profile')
    Driver = apps.get_model('mishwari_main_app', 'Driver')
    
    for profile in Profile.objects.filter(role='driver'):
        try:
            driver = Driver.objects.get(user=profile.user)
            if driver.operator.platform_user == profile.user:
                profile.role = 'standalone_driver'
            else:
                profile.role = 'invited_driver'
            profile.save()
        except Driver.DoesNotExist:
            # Edge case: profile with driver role but no Driver record
            profile.role = 'standalone_driver'
            profile.save()


class Migration(migrations.Migration):
    dependencies = [
        ('mishwari_main_app', '0016_remove_bus_amenities'),
    ]
    
    operations = [
        migrations.RunPython(migrate_roles),
    ]
