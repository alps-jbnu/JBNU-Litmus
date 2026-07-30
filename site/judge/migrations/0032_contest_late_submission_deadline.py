from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0031_profile_login_lock_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='contest',
            name='late_submission_deadline',
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='late submission deadline'),
        ),
    ]
