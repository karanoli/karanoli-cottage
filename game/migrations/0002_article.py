"""新增博客文章数据表。"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("game", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Article",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160, verbose_name="标题")),
                ("slug", models.SlugField(max_length=180, unique=True, verbose_name="网址标识")),
                ("summary", models.TextField(blank=True, help_text="用于首页和文章列表；留空时自动截取正文。", verbose_name="摘要")),
                ("content", models.TextField(help_text="支持 Markdown；LaTeX 行内公式使用 $...$，独立公式使用 $$...$$。", verbose_name="正文")),
                ("status", models.CharField(choices=[("draft", "草稿"), ("published", "已发布")], default="draft", max_length=12, verbose_name="状态")),
                ("published_at", models.DateTimeField(blank=True, null=True, verbose_name="发布时间")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
            ],
            options={"verbose_name": "文章", "verbose_name_plural": "文章", "ordering": ["-published_at", "-created_at"]},
        ),
    ]
