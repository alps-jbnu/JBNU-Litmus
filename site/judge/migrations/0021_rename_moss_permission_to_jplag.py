from django.conf import settings
from django.db import migrations


def _rename_permission(apps, schema_editor, old_code, old_name, new_code, new_name):
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))

    try:
        content_type = ContentType.objects.get(app_label='judge', model='contest')
    except ContentType.DoesNotExist:
        return

    old_perm = Permission.objects.filter(content_type=content_type, codename=old_code).first()
    new_perm = Permission.objects.filter(content_type=content_type, codename=new_code).first()

    if old_perm and not new_perm:
        old_perm.codename = new_code
        old_perm.name = new_name
        old_perm.save(update_fields=['codename', 'name'])
        return

    if old_perm and new_perm:
        group_perm_table = Group._meta.get_field('permissions').remote_field.through._meta.db_table
        user_perm_table = User._meta.get_field('user_permissions').remote_field.through._meta.db_table
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                f'UPDATE {group_perm_table} SET permission_id = %s WHERE permission_id = %s',
                [new_perm.id, old_perm.id],
            )
            cursor.execute(
                f'UPDATE {user_perm_table} SET permission_id = %s WHERE permission_id = %s',
                [new_perm.id, old_perm.id],
            )
        old_perm.delete()
        new_perm.name = new_name
        new_perm.save(update_fields=['name'])
        return

    if new_perm:
        new_perm.name = new_name
        new_perm.save(update_fields=['name'])


def forwards(apps, schema_editor):
    _rename_permission(
        apps,
        schema_editor,
        old_code='moss_contest',
        old_name='MOSS contest',
        new_code='jplag_contest',
        new_name='JPlag contest',
    )


def backwards(apps, schema_editor):
    _rename_permission(
        apps,
        schema_editor,
        old_code='jplag_contest',
        old_name='JPlag contest',
        new_code='moss_contest',
        new_name='MOSS contest',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0020_rename_contestmoss_to_contestjplag'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
