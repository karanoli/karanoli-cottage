"""博客文章、用户资产、数独题库、游戏过程与投稿的数据模型。"""

from datetime import timedelta
from pathlib import Path
import re

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


DIFFICULTIES = [("easy", "简单"), ("medium", "中等"), ("hard", "困难"), ("expert", "专家")]


def empty_notes():
    """为每个游戏会话创建互不共享的 9×9 候选数容器。"""
    return [[[] for _ in range(9)] for _ in range(9)]


def empty_grid():
    """创建 9×9 零矩阵，用于保存尚未改正的错误输入。"""
    return [[0 for _ in range(9)] for _ in range(9)]


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"

    source_file = models.FileField(
        "Markdown 文件",
        upload_to="articles/%Y/%m/",
        validators=[FileExtensionValidator(["md", "markdown"])],
    )
    title = models.CharField("标题", max_length=160, blank=True)
    slug = models.SlugField("网址标识", max_length=180, unique=True, blank=True, allow_unicode=True)
    summary = models.TextField("摘要", blank=True, help_text="用于首页和文章列表；留空时自动截取正文。")
    content = models.TextField("正文", blank=True, help_text="由上传的 Markdown 文件自动读取。")
    status = models.CharField("状态", max_length=12, choices=Status.choices, default=Status.PUBLISHED)
    published_at = models.DateTimeField("发布时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "文章"
        verbose_name_plural = "文章"

    def save(self, *args, **kwargs):
        # Markdown 文件是正文的唯一来源：保存时同步正文并补全展示字段。
        if self.source_file:
            source = self.source_file.file
            source.seek(0)
            # utf-8-sig 同时兼容普通 UTF-8 与带 BOM 的 Markdown 文件。
            self.content = source.read().decode("utf-8-sig")
            source.seek(0)
            # 仅在首次导入且标题为空时使用文件名；后续后台修改标题时绝不覆盖。
            # Path.stem 只移除最后一个扩展名，因此“算法笔记.v2.md”会得到“算法笔记.v2”。
            if not self.title:
                self.title = Path(self.source_file.name).stem
            if not self.summary:
                # 跳过标题、代码围栏、公式分隔等结构行，从首个正文段落生成摘要。
                paragraphs = re.split(r"\n\s*\n", self.content)
                for paragraph in paragraphs:
                    plain = " ".join(line.strip() for line in paragraph.splitlines()
                                     if line.strip() and not line.lstrip().startswith(("#", "```", "$$", "---")))
                    if plain:
                        self.summary = plain[:220]
                        break
        if not self.slug:
            # 网址标识冲突时追加递增后缀，避免覆盖已有文章。
            base_slug = slugify(self.title, allow_unicode=True) or f"article-{timezone.now():%Y%m%d%H%M%S}"
            candidate, suffix = base_slug, 2
            while Article.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base_slug}-{suffix}"
                suffix += 1
            self.slug = candidate
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ArticleComment(models.Model):
    """文章下的纯文本评论；用户由登录会话绑定，管理员可隐藏不合适的内容。"""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="comments", verbose_name="文章")
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="article_comments", verbose_name="用户")
    content = models.TextField("评论内容", max_length=2000)
    is_visible = models.BooleanField("公开显示", default=True)
    created_at = models.DateTimeField("评论时间", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "文章评论"
        verbose_name_plural = "文章评论"

    def __str__(self):
        return f"{self.user.username if self.user else '已注销用户'}：{self.content[:40]}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    coins = models.PositiveIntegerField(default=0)
    free_hints_remaining = models.PositiveSmallIntegerField(default=3)
    free_hints_date = models.DateField(default=timezone.localdate)

    def refresh_daily_hints(self):
        """跨日访问时重置免费提示次数。"""
        today = timezone.localdate()
        if self.free_hints_date != today:
            self.free_hints_remaining = getattr(settings, "SUDOKU_DAILY_FREE_HINTS", 3)
            self.free_hints_date = today
            self.save(update_fields=["free_hints_remaining", "free_hints_date"])

    def __str__(self):
        return f"{self.user.username}：{self.coins} 金币"


class PuzzleGroup(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTIES)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class Puzzle(models.Model):
    group = models.ForeignKey(PuzzleGroup, on_delete=models.CASCADE, related_name="puzzles")
    title = models.CharField(max_length=100)
    puzzle = models.JSONField(help_text="9×9，空格用 0")
    solution = models.JSONField(help_text="完整 9×9 答案")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTIES)
    sequence = models.PositiveIntegerField(default=1)
    contributor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="contributed_puzzles")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence", "id"]
        constraints = [models.UniqueConstraint(fields=["group", "sequence"], name="unique_group_sequence")]

    def clean(self):
        """后台保存题目时同时检查题面、答案和两者一致性。"""
        from .sudoku import validate_complete_solution, validate_puzzle
        errors = validate_puzzle(self.puzzle, self.solution)
        errors += validate_complete_solution(self.solution)
        if errors:
            raise ValidationError({"puzzle": errors})

    def __str__(self):
        return f"{self.group.name} · {self.title}"


class GameSession(models.Model):
    STATUS = [("playing", "进行中"), ("completed", "已完成"), ("failed", "已失败")]
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="game_sessions")
    guest_key = models.CharField(max_length=40, blank=True, db_index=True)
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE, related_name="sessions")
    board = models.JSONField()
    # 正确棋盘与错误显示分开保存，避免错误数字干扰提示和完成判定。
    wrong_values = models.JSONField(default=empty_grid)
    notes = models.JSONField(default=empty_notes)
    notes_visible = models.BooleanField(default=True)
    error_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=10, choices=STATUS, default="playing")
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    elapsed_seconds = models.PositiveIntegerField(default=0)
    last_saved_at = models.DateTimeField(auto_now=True)
    reward_granted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-last_saved_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "puzzle"], condition=models.Q(user__isnull=False), name="one_user_session_per_puzzle"),
            models.UniqueConstraint(fields=["guest_key", "puzzle"], condition=~models.Q(guest_key=""), name="one_guest_session_per_puzzle"),
        ]

    @property
    def duration(self):
        return timedelta(seconds=self.elapsed_seconds)

    def __str__(self):
        owner = self.user.username if self.user else f"游客 {self.guest_key[:6]}"
        return f"{owner} · {self.puzzle} · {self.get_status_display()}"


class MoveLog(models.Model):
    session = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name="moves")
    row = models.PositiveSmallIntegerField()
    col = models.PositiveSmallIntegerField()
    previous_value = models.PositiveSmallIntegerField(default=0)
    new_value = models.PositiveSmallIntegerField(default=0)
    previous_notes = models.JSONField(default=list)
    is_error = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class HintLog(models.Model):
    PAYMENT = [("free", "每日免费"), ("coin", "金币")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="hint_logs")
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE)
    session = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name="hint_logs")
    level = models.CharField(max_length=10, default="auto")
    technique = models.CharField(max_length=60)
    explanation = models.TextField()
    payment_type = models.CharField(max_length=10, choices=PAYMENT)
    cost = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class CoinTransaction(models.Model):
    TYPES = [("reward", "完成奖励"), ("hint", "提示消耗"), ("contribution", "贡献奖励"), ("admin", "后台调整")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="coin_transactions")
    amount = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    transaction_type = models.CharField(max_length=20, choices=TYPES)
    description = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PuzzleSubmission(models.Model):
    STATUS = [("draft", "待确认"), ("pending", "待审核"), ("approved", "已入库"), ("rejected", "已拒绝")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="puzzle_submissions")
    # 直接录入题面时不需要图片；图片模式仍由表单强制要求上传文件。
    puzzle_image = models.ImageField(upload_to="submissions/%Y/%m/", blank=True)
    # 兼容旧投稿数据；新版前台只录入题面，答案由求解器自动生成。
    solution_image = models.ImageField(upload_to="submissions/%Y/%m/", blank=True)
    recognized_puzzle = models.JSONField(default=list)
    recognized_solution = models.JSONField(default=list)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTIES, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    validation_errors = models.JSONField(default=list)
    rejection_reason = models.TextField(blank=True)
    created_puzzle = models.OneToOneField(Puzzle, null=True, blank=True, on_delete=models.SET_NULL, related_name="source_submission")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} 的投稿 #{self.pk}"
