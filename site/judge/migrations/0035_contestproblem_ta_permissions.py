from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0034_profile_unique_school_student_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='contestproblem',
            name='ta_access_restricted',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name='contestproblem',
            name='ta_permission_targets',
            field=models.ManyToManyField(
                blank=True,
                related_name='ta_accessible_contest_problems',
                to='judge.profile',
                verbose_name='TA 권한 허용 대상',
            ),
        ),
    ]
