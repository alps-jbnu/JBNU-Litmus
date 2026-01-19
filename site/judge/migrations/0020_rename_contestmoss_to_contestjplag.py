from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0019_auto_20250904_1931'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ContestMoss',
            new_name='ContestJplag',
        ),
        migrations.AlterModelOptions(
            name='contestjplag',
            options={
                'verbose_name': 'contest jplag result',
                'verbose_name_plural': 'contest jplag results',
            },
        ),
        migrations.AlterField(
            model_name='contestjplag',
            name='contest',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='contest_jplag',
                to='judge.contest',
                verbose_name='contest',
            ),
        ),
        migrations.AlterField(
            model_name='contestjplag',
            name='problem',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='contest_jplag',
                to='judge.problem',
                verbose_name='problem',
            ),
        ),
    ]
