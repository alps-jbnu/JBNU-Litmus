from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0030_profile_site_theme'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='failed_login_attempts',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='failed login attempts'),
        ),
        migrations.AddField(
            model_name='profile',
            name='login_locked_until',
            field=models.DateTimeField(blank=True, null=True, verbose_name='login locked until'),
        ),
    ]
