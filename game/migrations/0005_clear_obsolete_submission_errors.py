from django.db import migrations


def clear_draft_errors(apps, schema_editor):
    """旧流程可能留下“答案未填写”等提示，新流程不再需要这些信息。"""
    PuzzleSubmission = apps.get_model("game", "PuzzleSubmission")
    PuzzleSubmission.objects.filter(status="draft").update(validation_errors=[])


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0004_puzzlesubmission_solution_image_optional"),
    ]

    operations = [
        migrations.RunPython(clear_draft_errors, migrations.RunPython.noop),
    ]
