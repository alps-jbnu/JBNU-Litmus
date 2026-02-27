from django.db import migrations


def rename_department(apps, schema_editor):
    Department = apps.get_model('judge', 'Department')
    Department.objects.filter(name='기타').update(name='중/고등학생')


def reverse_rename_department(apps, schema_editor):
    Department = apps.get_model('judge', 'Department')
    Department.objects.filter(name='중/고등학생').update(name='기타')


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0026_add_school_model'),
    ]

    operations = [
        migrations.RunPython(rename_department, reverse_rename_department),
    ]
