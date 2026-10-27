import game.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0006_puzzlesubmission_image_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="gamesession",
            name="wrong_values",
            field=models.JSONField(default=game.models.empty_grid),
        ),
    ]
