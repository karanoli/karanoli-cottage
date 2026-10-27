"""注册与数独投稿所使用的表单及文件校验。"""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import ArticleComment, PuzzleSubmission


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=False, label="邮箱")

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")


class ArticleCommentForm(forms.ModelForm):
    """仅接收评论正文，文章与作者均由视图确定，避免客户端冒用他人身份。"""

    content = forms.CharField(
        label="评论内容", max_length=2000, strip=True,
        error_messages={"required": "请输入评论内容。", "max_length": "评论不能超过 2000 个字。"},
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "分享你的想法，友善交流。", "maxlength": 2000}),
    )

    class Meta:
        model = ArticleComment
        fields = ("content",)


class SubmissionUploadForm(forms.ModelForm):
    ENTRY_MODES = (
        ("image", "上传题目图片"),
        ("manual", "直接输入题面"),
    )

    # 投稿人可在同一入口选择图片识别或空白棋盘录入。
    entry_mode = forms.ChoiceField(
        choices=ENTRY_MODES,
        initial="image",
        widget=forms.RadioSelect,
        label="录入方式",
    )
    puzzle_image = forms.ImageField(
        required=False,
        label="题目图片",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )

    class Meta:
        model = PuzzleSubmission
        # 玩家只负责提供题面；完整答案由服务端在唯一解校验后生成。
        fields = ("puzzle_image",)

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("entry_mode")
        image = cleaned.get("puzzle_image")
        if mode == "image" and not image:
            self.add_error("puzzle_image", "请选择一张题目图片，或改用“直接输入题面”。")
        if image and image.size > 8 * 1024 * 1024:
            self.add_error("puzzle_image", "图片不能超过 8 MB")
        return cleaned
