from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0021_rename_moss_permission_to_jplag'),
    ]

    operations = [
        migrations.AddField(
            model_name='problem',
            name='is_contest_problem',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text='대회 문제로 설정하면 관리 권한자 또는 대회 참가자만 접근할 수 있습니다.',
                verbose_name='contest-only problem',
            ),
        ),
        migrations.AlterModelOptions(
            name='problem',
            options={
                'permissions': (
                    ('see_private_problem', 'See hidden problems'),
                    ('edit_own_problem', 'Edit own problems'),
                    ('edit_all_problem', 'Edit all problems'),
                    ('edit_public_problem', 'Edit all public problems'),
                    ('view_all_problem', 'View all problems'),
                    ('manage_contest_problem', 'Manage contest problems'),
                    ('problem_full_markup', 'Edit problems with full markup'),
                    ('clone_problem', 'Clone problem'),
                    ('change_public_visibility', 'Change is_public field'),
                    ('change_manually_managed', 'Change is_manually_managed field'),
                ),
                'verbose_name': 'problem',
                'verbose_name_plural': 'problems',
            },
        ),
    ]
