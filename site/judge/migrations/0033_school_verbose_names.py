from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0032_contest_late_submission_deadline'),
    ]

    operations = [
        migrations.AlterField(
            model_name='school',
            name='school_type',
            field=models.CharField(
                choices=[('university', '대학교'), ('highschool', '고등학교'), ('middleschool', '중학교')],
                max_length=20,
                verbose_name='학교 유형',
            ),
        ),
        migrations.AlterField(
            model_name='school',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='활성 여부'),
        ),
    ]
