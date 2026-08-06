from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0033_profile_student_number'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='profile',
            constraint=models.UniqueConstraint(
                fields=('school', 'student_number'),
                name='unique_school_student_number',
            ),
        ),
    ]
