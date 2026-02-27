from django.db import migrations, models
import django.db.models.deletion


def create_initial_data(apps, schema_editor):
    School = apps.get_model('judge', 'School')
    Profile = apps.get_model('judge', 'Profile')
    Contest = apps.get_model('judge', 'Contest')
    Department = apps.get_model('judge', 'Department')

    jbnu = School.objects.create(
        name='전북대학교',
        short_name='JBNU',
        school_type='university',
        is_jbnu=True,
        is_active=True,
    )

    Profile.objects.all().update(school_id=jbnu.id)
    Contest.objects.all().update(school_id=jbnu.id)

    Department.objects.get_or_create(name='중/고등학생')


def reverse_initial_data(apps, schema_editor):
    School = apps.get_model('judge', 'School')
    Profile = apps.get_model('judge', 'Profile')
    Contest = apps.get_model('judge', 'Contest')

    Profile.objects.all().update(school_id=None)
    Contest.objects.all().update(school_id=None)
    School.objects.filter(is_jbnu=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0025_merge_20260126_1755'),
    ]

    operations = [
        migrations.CreateModel(
            name='School',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='학교 이름')),
                ('short_name', models.CharField(max_length=20, verbose_name='약칭')),
                ('school_type', models.CharField(
                    choices=[('university', '대학교'), ('highschool', '고등학교'), ('middleschool', '중학교')],
                    max_length=20,
                )),
                ('is_jbnu', models.BooleanField(
                    default=False,
                    help_text='True이면 @jbnu.ac.kr 이메일 강제, False이면 @gmail.com 강제',
                    verbose_name='전북대 여부',
                )),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': '학교',
                'verbose_name_plural': '학교',
            },
        ),
        migrations.AddField(
            model_name='profile',
            name='school',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='judge.school',
                verbose_name='학교',
            ),
        ),
        migrations.AddField(
            model_name='contest',
            name='school',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='judge.school',
                verbose_name='학교',
                help_text='특정 학교 전용 대회/과제. 비워두면 전체 공개',
            ),
        ),
        migrations.RunPython(create_initial_data, reverse_initial_data),
    ]
