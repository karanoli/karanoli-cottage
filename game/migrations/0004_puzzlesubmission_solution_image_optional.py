from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0003_article_markdown_upload"),
    ]

    operations = [
        migrations.AlterField(
            model_name="puzzlesubmission",
            name="solution_image",
            field=models.ImageField(blank=True, upload_to="submissions/%Y/%m/"),
        ),
    ]
