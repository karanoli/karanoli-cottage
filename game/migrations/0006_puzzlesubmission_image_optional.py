from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0005_clear_obsolete_submission_errors"),
    ]

    operations = [
        migrations.AlterField(
            model_name="puzzlesubmission",
            name="puzzle_image",
            field=models.ImageField(blank=True, upload_to="submissions/%Y/%m/"),
        ),
    ]
