"""将文章发布流程升级为 Markdown 文件上传。"""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("game", "0002_article")]

    operations = [
        migrations.AddField(
            model_name="article",
            name="source_file",
            field=models.FileField(upload_to="articles/%Y/%m/", validators=[django.core.validators.FileExtensionValidator(["md", "markdown"])], verbose_name="Markdown 文件"),
        ),
        migrations.AlterField(
            model_name="article",
            name="title",
            field=models.CharField(blank=True, max_length=160, verbose_name="标题"),
        ),
        migrations.AlterField(
            model_name="article",
            name="slug",
            field=models.SlugField(allow_unicode=True, blank=True, max_length=180, unique=True, verbose_name="网址标识"),
        ),
        migrations.AlterField(
            model_name="article",
            name="content",
            field=models.TextField(blank=True, help_text="由上传的 Markdown 文件自动读取。", verbose_name="正文"),
        ),
        migrations.AlterField(
            model_name="article",
            name="status",
            field=models.CharField(choices=[("draft", "草稿"), ("published", "已发布")], default="published", max_length=12, verbose_name="状态"),
        ),
    ]
