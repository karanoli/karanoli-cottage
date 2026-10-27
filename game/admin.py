"""后台管理配置：文章发布、题库维护、投稿审核与数据导出。"""

import json

from django import forms
from django.contrib import admin
from django.http import HttpResponse

from .models import (Article, ArticleComment, CoinTransaction, GameSession, HintLog, MoveLog,
                     Puzzle, PuzzleGroup, PuzzleSubmission, UserProfile)


class ArticleAdminForm(forms.ModelForm):
    """为文章后台提供面向管理员的中文填写说明。"""

    class Meta:
        model = Article
        fields = "__all__"
        help_texts = {
            "source_file": "请上传 UTF-8 编码的 .md 或 .markdown 文件。首次保存时，标题默认采用文件名并移除扩展名。",
            "title": "首次导入后可自由修改；再次保存或替换 Markdown 文件都不会覆盖这里的标题。",
            "slug": "文章网址中的唯一标识，支持中文；请勿填写斜杠 /。",
            "summary": "用于首页和文章列表；留空时系统会从正文自动提取。",
            "status": "选择“已发布”后，文章才会出现在前台页面。",
            "published_at": "留空时，文章首次发布会自动记录当前时间。",
            "content": "正文由上传的 Markdown 文件自动读取，无需在此手工填写。",
        }


class PuzzleGroupAdminForm(forms.ModelForm):
    """说明题组名称、网址标识和显示顺序的填写规则。"""

    class Meta:
        model = PuzzleGroup
        fields = "__all__"
        help_texts = {
            "name": "填写前台显示的题组名称，例如“每日练习”。",
            "slug": "题组网址标识，建议使用小写英文、数字和连字符，例如 daily-practice。",
            "description": "简要说明该题组的来源、特点或适用人群。",
            "difficulty": "该题组的默认难度，应与组内题目保持一致。",
            "sort_order": "数字越小越靠前显示；相同数字时按名称排序。",
        }


class PuzzleAdminForm(forms.ModelForm):
    """为数独题面、答案和展示信息增加中文格式提示。"""

    class Meta:
        model = Puzzle
        fields = "__all__"
        help_texts = {
            "group": "选择题目所属题组。",
            "title": "填写便于识别的题目名称，例如“每日练习 01”。",
            "puzzle": "填写 9×9 二维数组，空格用 0 表示；每行必须正好 9 个整数。",
            "solution": "填写完整 9×9 答案；每行、每列、每宫都必须包含 1 至 9。",
            "difficulty": "选择题目难度，应与所属题组的难度一致。",
            "sequence": "题目在所属题组中的顺序，数字越小越靠前。",
            "contributor": "可选；记录提供该题目的用户。",
            "is_active": "取消勾选后，题目不会出现在前台难度选择和游戏列表中。",
        }
        widgets = {
            "puzzle": forms.Textarea(attrs={"rows": 10, "placeholder": "示例：[[0, 0, ...], ..., [0, 0, ...]]"}),
            "solution": forms.Textarea(attrs={"rows": 10, "placeholder": "示例：[[1, 2, ...], ..., [8, 9, ...]]"}),
        }


class PuzzleSubmissionAdminForm(forms.ModelForm):
    """提示管理员如何复核 OCR 题面、程序答案与审核意见。"""

    class Meta:
        model = PuzzleSubmission
        fields = "__all__"
        help_texts = {
            "difficulty": "投稿人选择的预期难度，审核时可结合题目实际情况调整。",
            "puzzle_image": "图片录入时应上传清晰完整的题面；直接输入方式可以不上传图片。",
            "solution_image": "旧版兼容字段；当前投稿流程不需要上传答案图片。",
            "recognized_puzzle": "OCR 得到的题面数组；入库前请人工核对，空格使用 0。",
            "recognized_solution": "由程序在唯一解确认后自动生成的完整答案。",
            "status": "审核通过前先完成题面图片、数组、程序答案和唯一解检查。",
            "rejection_reason": "驳回时填写具体原因，方便投稿人修改后重新提交。",
            "puzzle": "审核通过并入库后，系统会在此关联生成的正式题目。",
        }


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    form = ArticleAdminForm
    list_display = ("title", "status", "published_at", "updated_at")
    list_filter = ("status", "published_at")
    search_fields = ("title", "summary", "content")
    date_hierarchy = "published_at"
    readonly_fields = ("content", "created_at", "updated_at")

    def get_fields(self, request, obj=None):
        # 新建文章时只要求上传 Markdown，标题默认取不含扩展名的文件名。
        if obj is None:
            return ("source_file",)
        # 编辑页保留自动生成字段，方便管理员修正标题、摘要和发布状态。
        return ("source_file", "title", "slug", "summary", "status", "published_at",
                "content", "created_at", "updated_at")


@admin.register(PuzzleGroup)
class PuzzleGroupAdmin(admin.ModelAdmin):
    form = PuzzleGroupAdminForm
    list_display = ("name", "difficulty", "sort_order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Puzzle)
class PuzzleAdmin(admin.ModelAdmin):
    form = PuzzleAdminForm
    list_display = ("title", "group", "difficulty", "sequence", "is_active")
    list_filter = ("difficulty", "group", "is_active")
    search_fields = ("title",)
    actions = ("export_json",)

    @admin.action(description="导出所选题目为 JSON")
    def export_json(self, request, queryset):
        # 导出格式与 import_puzzles 命令保持一致，方便题库迁移和备份。
        payload = [{
            "group": item.group.slug, "title": item.title, "puzzle": item.puzzle,
            "solution": item.solution, "difficulty": item.difficulty, "sequence": item.sequence,
        } for item in queryset.select_related("group")]
        response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2), content_type="application/json")
        response["Content-Disposition"] = 'attachment; filename="sudoku-puzzles.json"'
        return response


@admin.register(ArticleComment)
class ArticleCommentAdmin(admin.ModelAdmin):
    """按文章、作者检索评论，并提供批量隐藏和恢复操作。"""

    list_display = ("user", "article", "preview", "is_visible", "created_at")
    list_filter = ("is_visible", "created_at")
    search_fields = ("article__title", "user__username", "content")
    list_select_related = ("user", "article")
    readonly_fields = ("article", "user", "content", "created_at")
    actions = ("hide_comments", "show_comments")

    @admin.display(description="评论内容")
    def preview(self, obj):
        return obj.content[:80]

    def has_add_permission(self, request):
        return False

    @admin.action(description="隐藏所选评论")
    def hide_comments(self, request, queryset):
        queryset.update(is_visible=False)

    @admin.action(description="恢复显示所选评论")
    def show_comments(self, request, queryset):
        queryset.update(is_visible=True)


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("puzzle", "user", "guest_key", "status", "error_count", "elapsed_seconds", "last_saved_at")
    list_filter = ("status", "puzzle__difficulty")
    readonly_fields = ("started_at", "last_saved_at")


@admin.register(PuzzleSubmission)
class PuzzleSubmissionAdmin(admin.ModelAdmin):
    form = PuzzleSubmissionAdminForm
    list_display = ("id", "user", "difficulty", "status", "created_at")
    list_filter = ("status", "difficulty")


admin.site.register(UserProfile)
admin.site.register(HintLog)
admin.site.register(CoinTransaction)
admin.site.register(MoveLog)
