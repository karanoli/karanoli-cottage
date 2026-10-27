"""核心数独算法、文章权限、账户和完整网页流程的回归测试。"""

import json
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Article, ArticleComment, GameSession, Puzzle, PuzzleGroup, PuzzleSubmission
from .sudoku import count_solutions, find_hint, solve_grid, validate_puzzle


SOLUTION = [[5,3,4,6,7,8,9,1,2],[6,7,2,1,9,5,3,4,8],[1,9,8,3,4,2,5,6,7],
            [8,5,9,7,6,1,4,2,3],[4,2,6,8,5,3,7,9,1],[7,1,3,9,2,4,8,5,6],
            [9,6,1,5,3,7,2,8,4],[2,8,7,4,1,9,6,3,5],[3,4,5,2,8,6,1,7,9]]
PUZZLE = [[5,3,0,0,7,0,0,0,0],[6,0,0,1,9,5,0,0,0],[0,9,8,0,0,0,0,6,0],
          [8,0,0,0,6,0,0,0,3],[4,0,0,8,0,3,0,0,1],[7,0,0,0,2,0,0,0,6],
          [0,6,0,0,0,0,2,8,0],[0,0,0,4,1,9,0,0,5],[0,0,0,0,8,0,0,7,9]]


class SudokuEngineTests(TestCase):
    def test_solver_and_unique_solution(self):
        self.assertEqual(solve_grid(PUZZLE), SOLUTION)
        self.assertEqual(count_solutions(PUZZLE), 1)
        self.assertEqual(validate_puzzle(PUZZLE, SOLUTION), [])

    def test_hint_is_explanatory(self):
        board = [row[:] for row in SOLUTION]
        board[0][0] = 0
        hint = find_hint(board)
        self.assertEqual(hint["technique"], "唯一候选数")
        self.assertIn("唯一候选数", hint["explanation"])
        self.assertEqual(hint["placement"]["value"], 5)


class ArticleTests(TestCase):
    def setUp(self):
        self.published = Article.objects.create(
            title="公式与小屋",
            slug="math-and-cottage",
            summary="一篇测试文章",
            content="# 标题\n\n行内公式 $a^2+b^2=c^2$。\n\n$$\\sum_{i=1}^n i$$",
            status=Article.Status.PUBLISHED,
        )
        self.draft = Article.objects.create(
            title="未发布草稿",
            slug="draft-note",
            content="暂不公开",
            status=Article.Status.DRAFT,
        )

    def test_only_published_articles_are_public(self):
        response = self.client.get(reverse("article-list"))
        self.assertContains(response, self.published.title)
        self.assertNotContains(response, self.draft.title)
        self.assertEqual(self.client.get(reverse("article-detail", args=[self.draft.slug])).status_code, 404)

    def test_article_detail_loads_markdown_and_katex(self):
        response = self.client.get(reverse("article-detail", args=[self.published.slug]))
        self.assertContains(response, "marked.umd.js")
        self.assertContains(response, "katex.min.js")
        self.assertContains(response, "highlight.js")
        self.assertContains(response, "hljs.highlightElement")
        self.assertContains(response, 'id="article-source"')
        self.assertContains(response, "protectDisplayMath")
        self.assertContains(response, 'data-math-index')

    def test_future_article_is_not_public(self):
        self.published.published_at = timezone.now() + timedelta(days=1)
        self.published.save(update_fields=["published_at"])
        self.assertEqual(self.client.get(reverse("article-detail", args=[self.published.slug])).status_code, 404)

    def test_only_admin_can_open_article_editor(self):
        normal_user = User.objects.create_user("reader", password="reader-pass-123")
        self.client.force_login(normal_user)
        response = self.client.get(reverse("admin:game_article_add"))
        self.assertEqual(response.status_code, 302)

        admin_user = User.objects.create_superuser("editor", password="editor-pass-123")
        self.client.force_login(admin_user)
        response = self.client.get(reverse("admin:game_article_add"))
        self.assertEqual(response.status_code, 200)

    def test_markdown_upload_creates_published_article(self):
        markdown = "# 文档内的一级标题\n\n这是自动生成的摘要。\n\n公式：$x^2$。".encode()
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            article = Article.objects.create(
                source_file=SimpleUploadedFile("upload-test.md", markdown, content_type="text/markdown")
            )
            # 默认标题来自原文件名，而不是 Markdown 正文中的一级标题。
            self.assertEqual(article.title, "upload-test")
            self.assertEqual(article.slug, "upload-test")
            self.assertEqual(article.summary, "这是自动生成的摘要。")
            self.assertEqual(article.status, Article.Status.PUBLISHED)
            self.assertIn("$x^2$", article.content)

            # 管理员保存修改后的标题时，不应再次被文件名或正文标题覆盖。
            article.title = "管理员修改后的标题"
            article.save()
            article.refresh_from_db()
            self.assertEqual(article.title, "管理员修改后的标题")

    def test_chinese_slug_can_reverse_and_open(self):
        """中文标题生成的 slug 必须能反向生成网址并正常访问。"""
        article = Article.objects.create(
            title="中文文章", slug="中文文章", content="# 中文文章",
            status=Article.Status.PUBLISHED,
        )
        url = reverse("article-detail", args=[article.slug])
        self.assertEqual(url, "/articles/%E4%B8%AD%E6%96%87%E6%96%87%E7%AB%A0/")
        self.assertEqual(self.client.get(url).status_code, 200)


class ArticleCommentTests(TestCase):
    """验证评论的身份、内容安全、可见范围与注册回跳，避免公开后出现越权。"""

    def setUp(self):
        self.article = Article.objects.create(title="评论测试", slug="comment-test", content="正文")
        self.user = User.objects.create_user("commenter", password="comment-pass-123")
        self.other = User.objects.create_user("another-reader", password="other-pass-123")
        self.detail_url = reverse("article-detail", args=[self.article.slug])
        self.create_url = reverse("article-comment-create", args=[self.article.slug])

    def test_guest_reads_comments_and_sees_registration_prompt(self):
        ArticleComment.objects.create(article=self.article, user=self.user, content="公开评论")
        response = self.client.get(self.detail_url)
        self.assertContains(response, "公开评论")
        self.assertContains(response, "注册并评论")
        self.assertNotContains(response, 'class="comment-form"')
        response = self.client.post(self.create_url, {"content": "游客越权"})
        self.assertRedirects(response, f"{reverse('login')}?next={self.create_url}")
        self.assertEqual(self.article.comments.count(), 1)

    def test_author_is_bound_to_login_and_refresh_does_not_repost(self):
        self.client.force_login(self.user)
        response = self.client.post(self.create_url, {"content": "  文章很有帮助  ", "user": self.other.pk})
        comment = self.article.comments.get()
        self.assertEqual(comment.user, self.user)
        self.assertEqual(comment.content, "文章很有帮助")
        self.assertRedirects(response, f"{self.detail_url}#comment-{comment.pk}")
        self.client.get(response.url)
        self.assertEqual(self.article.comments.count(), 1)

    def test_blank_or_oversized_comments_keep_validation_errors(self):
        self.client.force_login(self.user)
        for value in (" \n\t ", "字" * 2001):
            response = self.client.post(self.create_url, {"content": value})
            self.assertEqual(response.status_code, 400)
            self.assertTrue(response.context["comment_form"].errors)
        self.assertFalse(self.article.comments.exists())

    def test_comments_are_escaped_and_hidden_comments_are_not_public(self):
        ArticleComment.objects.create(article=self.article, user=self.user, content='<script>alert("x")</script>\n第二行')
        ArticleComment.objects.create(article=self.article, user=self.other, content="隐藏内容", is_visible=False)
        response = self.client.get(self.detail_url)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "<br>第二行")
        self.assertNotContains(response, "隐藏内容")
        self.assertEqual(response.context["comment_count"], 1)

    def test_draft_and_future_articles_cannot_receive_comments(self):
        self.client.force_login(self.user)
        self.article.status = Article.Status.DRAFT
        self.article.save()
        self.assertEqual(self.client.post(self.create_url, {"content": "越权"}).status_code, 404)
        self.article.status = Article.Status.PUBLISHED
        self.article.published_at = timezone.now() + timedelta(days=1)
        self.article.save()
        self.assertEqual(self.client.post(self.create_url, {"content": "越权"}).status_code, 404)
        self.assertFalse(self.article.comments.exists())

    def test_only_author_can_delete_comment_and_deletion_requires_post(self):
        comment = ArticleComment.objects.create(article=self.article, user=self.user, content="作者评论")
        url = reverse("article-comment-delete", args=[comment.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(ArticleComment.objects.filter(pk=comment.pk).exists())
        self.assertRedirects(self.client.post(url), f"{self.detail_url}#comments")
        self.assertFalse(ArticleComment.objects.filter(pk=comment.pk).exists())

    def test_comments_are_paginated_and_post_requires_csrf(self):
        ArticleComment.objects.bulk_create([
            ArticleComment(article=self.article, user=self.user, content=f"评论 {i}") for i in range(21)
        ])
        response = self.client.get(self.detail_url)
        self.assertEqual(len(response.context["comments_page"]), 20)
        self.assertEqual(response.context["comment_count"], 21)
        response = self.client.get(self.detail_url, {"comments_page": 2})
        self.assertEqual(len(response.context["comments_page"]), 1)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.create_url, {"content": "无令牌"}).status_code, 403)

    def test_registration_returns_to_article_and_rejects_external_redirect(self):
        target = f"{self.detail_url}#comments"
        response = self.client.post(reverse("register"), {
            "username": "new-reader", "password1": "new-reader-pass-123", "password2": "new-reader-pass-123",
            "next": target,
        })
        self.assertRedirects(response, target)
        self.client.logout()
        response = self.client.post(reverse("register"), {
            "username": "safe-reader", "password1": "another-strong-phrase-987", "password2": "another-strong-phrase-987",
            "next": "https://example.com/phishing",
        })
        self.assertRedirects(response, reverse("group-list"))

    def test_admin_can_hide_and_restore_comment(self):
        comment = ArticleComment.objects.create(article=self.article, user=self.user, content="待管理评论")
        admin = User.objects.create_superuser("comment-admin", password="admin-pass-123")
        self.client.force_login(admin)
        url = reverse("admin:game_articlecomment_changelist")
        self.assertEqual(self.client.get(url).status_code, 200)
        for action, expected in (("hide_comments", False), ("show_comments", True)):
            response = self.client.post(url, {"action": action, "_selected_action": [comment.pk]})
            self.assertEqual(response.status_code, 302)
            comment.refresh_from_db()
            self.assertEqual(comment.is_visible, expected)


class WebFlowTests(TestCase):
    def setUp(self):
        self.easy = PuzzleGroup.objects.create(name="简单", slug="easy", difficulty="easy")
        self.medium = PuzzleGroup.objects.create(name="中等", slug="medium", difficulty="medium")
        self.puzzle = Puzzle.objects.create(group=self.easy, title="测试题", puzzle=PUZZLE,
                                            solution=SOLUTION, difficulty="easy", sequence=1)
        self.medium_puzzle = Puzzle.objects.create(group=self.medium, title="中等题", puzzle=PUZZLE,
                                                   solution=SOLUTION, difficulty="medium", sequence=1)
        self.user = User.objects.create_user("learner", password="strong-pass-123")

    def test_home_is_blog_landing_page(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "karanoli的小屋")
        self.assertContains(response, "小游戏室")
        self.assertContains(response, "game/images/karanoli-icon.jpeg")
        self.assertNotContains(response, "数独研习社")

    def test_guest_can_play_easy_but_not_medium(self):
        self.assertEqual(self.client.get(reverse("game", args=[self.puzzle.id])).status_code, 200)
        response = self.client.get(reverse("game", args=[self.medium_puzzle.id]))
        self.assertRedirects(response, reverse("login"))

    def test_password_change_requires_login(self):
        response = self.client.get(reverse("password-change"))
        self.assertRedirects(response, f'{reverse("login")}?next={reverse("password-change")}')

    def test_user_can_change_password_without_being_logged_out(self):
        self.client.login(username="learner", password="strong-pass-123")
        response = self.client.post(reverse("password-change"), {
            "old_password": "strong-pass-123",
            "new_password1": "renewed-pass-456",
            "new_password2": "renewed-pass-456",
        })
        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("renewed-pass-456"))
        # 修改密码后当前会话仍有效，用户不会被迫重新登录。
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

    def test_difficulty_groups_use_explicit_progression_order(self):
        PuzzleGroup.objects.filter(pk=self.easy.pk).update(sort_order=0)
        PuzzleGroup.objects.filter(pk=self.medium.pk).update(sort_order=1)
        hard = PuzzleGroup.objects.create(name="困难", slug="hard", difficulty="hard", sort_order=2)
        expert = PuzzleGroup.objects.create(name="专家", slug="expert", difficulty="expert", sort_order=3)
        self.client.force_login(self.user)
        response = self.client.get(reverse("group-list"))
        self.assertEqual(
            [group.slug for group in response.context["groups"]],
            [self.easy.slug, self.medium.slug, hard.slug, expert.slug],
        )

    def test_guest_progress_is_cleared_when_page_is_reopened(self):
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(puzzle=self.puzzle, user__isnull=True)
        self.client.post(reverse("game-move", args=[session.id]),
                         json.dumps({"row": 0, "col": 2, "value": 4, "elapsed": 27}),
                         content_type="application/json")
        session.refresh_from_db()
        self.assertEqual(session.board[0][2], 4)

        response = self.client.get(reverse("game", args=[self.puzzle.id]))
        self.assertContains(response, "游客进度不会保存")
        self.assertContains(response, "Shift 切换小数字模式")
        session.refresh_from_db()
        self.assertEqual(session.board, PUZZLE)
        self.assertEqual(session.wrong_values, [[0] * 9 for _ in range(9)])
        self.assertEqual(session.elapsed_seconds, 0)
        self.assertEqual(session.status, "playing")

    def test_three_errors_fail_and_persist(self):
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        url = reverse("game-move", args=[session.id])
        for expected in range(1, 4):
            response = self.client.post(url, json.dumps({"row": 0, "col": 2, "value": 9}), content_type="application/json")
            self.assertEqual(response.json()["errors"], expected)
            self.assertTrue(response.json()["is_error"])
            self.assertEqual(response.json()["wrong_value"], 9)
        session.refresh_from_db()
        self.assertEqual(session.status, "failed")
        self.assertEqual(session.board, PUZZLE)
        self.assertEqual(session.wrong_values[0][2], 9)

    def test_failed_game_can_restart_from_result_dialog(self):
        """三次错误后的遮罩内必须能重开，并完整清除上一局状态。"""
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        move_url = reverse("game-move", args=[session.id])
        for value in (9, 8, 7):
            self.client.post(move_url, json.dumps({"row": 0, "col": 2, "value": value}),
                             content_type="application/json")

        response = self.client.get(reverse("game", args=[self.puzzle.id]))
        self.assertContains(response, "重新开始")
        self.assertContains(response, f'action="{reverse("reset-game", args=[self.puzzle.id])}"')

        response = self.client.post(reverse("reset-game", args=[self.puzzle.id]))
        self.assertRedirects(response, reverse("game", args=[self.puzzle.id]))
        session.refresh_from_db()
        self.assertEqual(session.status, "playing")
        self.assertEqual(session.error_count, 0)
        self.assertEqual(session.board, PUZZLE)
        self.assertEqual(session.wrong_values, [[0] * 9 for _ in range(9)])
        self.assertFalse(session.moves.exists())

    def test_new_game_opens_next_puzzle_and_preserves_current_progress(self):
        """右侧“新游戏”应进入下一题，而不是重置当前题。"""
        next_puzzle = Puzzle.objects.create(
            group=self.easy, title="测试题 2", puzzle=PUZZLE,
            solution=SOLUTION, difficulty="easy", sequence=2,
        )
        self.client.force_login(self.user)
        page = self.client.get(reverse("game", args=[self.puzzle.id]))
        self.assertContains(page, f'action="{reverse("new-game", args=[self.puzzle.id])}"')
        current_session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        current_board = [row[:] for row in PUZZLE]
        current_board[0][2] = 4
        current_session.board = current_board
        current_session.elapsed_seconds = 38
        current_session.save(update_fields=["board", "elapsed_seconds"])

        # 下一题即使有旧记录，也应以全新一局开始。
        self.client.get(reverse("game", args=[next_puzzle.id]))
        next_session = GameSession.objects.get(user=self.user, puzzle=next_puzzle)
        next_session.error_count = 2
        next_session.status = "failed"
        next_session.elapsed_seconds = 99
        next_session.save(update_fields=["error_count", "status", "elapsed_seconds"])

        response = self.client.post(reverse("new-game", args=[self.puzzle.id]))
        self.assertRedirects(response, reverse("game", args=[next_puzzle.id]))

        current_session.refresh_from_db()
        next_session.refresh_from_db()
        self.assertEqual(current_session.board[0][2], 4)
        self.assertEqual(current_session.elapsed_seconds, 38)
        self.assertEqual(next_session.board, PUZZLE)
        self.assertEqual(next_session.wrong_values, [[0] * 9 for _ in range(9)])
        self.assertEqual(next_session.error_count, 0)
        self.assertEqual(next_session.status, "playing")
        self.assertEqual(next_session.elapsed_seconds, 0)

    def test_new_game_restarts_current_only_when_group_has_one_puzzle(self):
        """题组仅有一题时，“新游戏”才循环回本题并开新局。"""
        self.client.force_login(self.user)
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        session.error_count = 2
        session.elapsed_seconds = 45
        session.save(update_fields=["error_count", "elapsed_seconds"])

        response = self.client.post(reverse("new-game", args=[self.puzzle.id]))
        self.assertRedirects(response, reverse("game", args=[self.puzzle.id]))
        session.refresh_from_db()
        self.assertEqual(session.error_count, 0)
        self.assertEqual(session.elapsed_seconds, 0)
        self.assertEqual(session.status, "playing")

    def test_wrong_number_stays_red_until_another_number_replaces_it(self):
        """错误值独立保存；换填仍错就继续计错，换填正确则转为正式数字。"""
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        url = reverse("game-move", args=[session.id])

        response = self.client.post(url, json.dumps({"row": 0, "col": 2, "value": 9}),
                                    content_type="application/json")
        self.assertEqual(response.json()["wrong_value"], 9)
        self.assertEqual(response.json()["errors"], 1)
        session.refresh_from_db()
        self.assertEqual(session.board[0][2], 0)
        self.assertEqual(session.wrong_values[0][2], 9)

        response = self.client.post(url, json.dumps({"row": 0, "col": 2, "value": 8}),
                                    content_type="application/json")
        self.assertEqual(response.json()["wrong_value"], 8)
        self.assertEqual(response.json()["errors"], 2)

        response = self.client.post(url, json.dumps({"row": 0, "col": 2, "value": 4}),
                                    content_type="application/json")
        self.assertFalse(response.json()["is_error"])
        self.assertEqual(response.json()["value"], 4)
        self.assertEqual(response.json()["wrong_value"], 0)
        self.assertEqual(response.json()["errors"], 2)
        session.refresh_from_db()
        self.assertEqual(session.board[0][2], 4)
        self.assertEqual(session.wrong_values[0][2], 0)

    def test_game_page_serializes_persisted_wrong_values(self):
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        wrong_values = [[0] * 9 for _ in range(9)]
        wrong_values[0][2] = 9
        session.wrong_values = wrong_values
        session.save(update_fields=["wrong_values"])

        response = self.client.get(reverse("game", args=[self.puzzle.id]))
        self.assertContains(response, 'id="wrong-values-data"')
        self.assertContains(response, "[[0, 0, 9")

    def test_notes_are_saved(self):
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        notes = [[[] for _ in range(9)] for _ in range(9)]
        notes[0][2] = [1, 2, 4]
        response = self.client.post(reverse("game-save", args=[session.id]),
                                    json.dumps({"notes": notes, "elapsed": 33}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.notes[0][2], [1, 2, 4])
        self.assertEqual(session.elapsed_seconds, 33)

    def test_correct_number_removes_matching_notes_from_row_column_and_box(self):
        """正确落子只清理相关格的同值小数字，不改动其他数字和无关格笔记。"""
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        notes = [[[] for _ in range(9)] for _ in range(9)]
        notes[0][3] = [2, 4, 6]  # 同行
        notes[1][2] = [1, 4, 7]  # 同列且同宫
        notes[1][1] = [4, 7]     # 同宫
        notes[4][4] = [4, 5]     # 与 R1C3 无关
        session.notes = notes
        session.save(update_fields=["notes"])

        response = self.client.post(
            reverse("game-move", args=[session.id]),
            json.dumps({"row": 0, "col": 2, "value": 4}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        updated = response.json()["notes"]
        self.assertEqual(updated[0][3], [2, 6])
        self.assertEqual(updated[1][2], [1, 7])
        self.assertEqual(updated[1][1], [7])
        self.assertEqual(updated[4][4], [4, 5])
        session.refresh_from_db()
        self.assertEqual(session.notes, updated)

    def test_wrong_number_does_not_remove_peer_notes(self):
        """错误红字不属于已确认棋盘，因此不能提前清除任何候选小数字。"""
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        notes = [[[] for _ in range(9)] for _ in range(9)]
        notes[0][3] = [6, 9]
        notes[1][2] = [4, 9]
        session.notes = notes
        session.save(update_fields=["notes"])

        response = self.client.post(
            reverse("game-move", args=[session.id]),
            json.dumps({"row": 0, "col": 2, "value": 9}),
            content_type="application/json",
        )
        self.assertTrue(response.json()["is_error"])
        self.assertEqual(response.json()["notes"], notes)
        session.refresh_from_db()
        self.assertEqual(session.notes, notes)

    def test_hint_uses_daily_free_allowance(self):
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        response = self.client.post(reverse("game-hint", args=[session.id]), "{}", content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.free_hints_remaining, 2)

    def test_hint_costs_100_coins_after_free_allowance(self):
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        profile = self.user.profile
        profile.free_hints_remaining = 0
        profile.coins = 100
        profile.save(update_fields=["free_hints_remaining", "coins"])
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        response = self.client.post(reverse("game-hint", args=[session.id]), "{}", content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cost"], 100)
        profile.refresh_from_db()
        self.assertEqual(profile.coins, 0)

    def test_easy_completion_rewards_10_coins(self):
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        board = [row[:] for row in SOLUTION]
        board[0][2] = 0
        session.board = board
        session.save(update_fields=["board"])
        response = self.client.post(reverse("game-move", args=[session.id]),
                                    json.dumps({"row": 0, "col": 2, "value": 4}),
                                    content_type="application/json")
        self.assertEqual(response.json()["reward"], 10)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.coins, 10)

    def test_confirmed_correct_number_cannot_be_overwritten(self):
        self.client.login(username="learner", password="strong-pass-123")
        self.client.get(reverse("game", args=[self.puzzle.id]))
        session = GameSession.objects.get(user=self.user, puzzle=self.puzzle)
        url = reverse("game-move", args=[session.id])
        response = self.client.post(url, json.dumps({"row": 0, "col": 2, "value": 4}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(url, json.dumps({"row": 0, "col": 2, "value": 5}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 409)
        session.refresh_from_db()
        self.assertEqual(session.board[0][2], 4)
        self.assertEqual(session.error_count, 0)

    def test_authenticated_pages_render(self):
        self.client.login(username="learner", password="strong-pass-123")
        for url in (reverse("profile"), reverse("submit-puzzle"),
                    reverse("puzzle-list", args=[self.medium.slug]),
                    reverse("game", args=[self.medium_puzzle.id])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_manual_submission_opens_blank_grid_without_image(self):
        """直接输入不要求图片，81 个值为 0 的格子在页面上应显示为空白。"""
        self.client.force_login(self.user)
        response = self.client.post(reverse("submit-puzzle"), {"entry_mode": "manual"})
        submission = PuzzleSubmission.objects.get(user=self.user)
        self.assertRedirects(response, reverse("confirm-submission", args=[submission.id]))
        self.assertEqual(submission.puzzle_image.name, "")
        self.assertEqual(submission.recognized_puzzle, [[0] * 9 for _ in range(9)])

        response = self.client.get(reverse("confirm-submission", args=[submission.id]))
        html = response.content.decode()
        self.assertEqual(html.count('aria-label="题面格"'), 81)
        self.assertEqual(html.count('value="" data-prefix="p"'), 81)
        self.assertNotContains(response, 'value="0"')

    def test_image_submission_still_requires_a_picture(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("submit-puzzle"), {"entry_mode": "image"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "请选择一张题目图片")
        self.assertFalse(PuzzleSubmission.objects.filter(user=self.user).exists())

    def test_recognized_image_grid_hides_zero_but_keeps_given_digits(self):
        """图片识别结果与直接输入共用显示规则：0 为空白，给定数字保留。"""
        self.client.force_login(self.user)
        submission = PuzzleSubmission.objects.create(
            user=self.user,
            puzzle_image="submissions/test.png",
            recognized_puzzle=PUZZLE,
        )
        response = self.client.get(reverse("confirm-submission", args=[submission.id]))
        self.assertContains(response, 'value="5" data-prefix="p"')
        self.assertNotContains(response, 'value="0"')

    def test_hint_badge_switches_from_allowance_to_coin_price(self):
        self.client.login(username="learner", password="strong-pass-123")
        response = self.client.get(reverse("game", args=[self.puzzle.id]))
        self.assertContains(response, 'id="hint-badge">3</i>')
        profile = self.user.profile
        profile.free_hints_remaining = 0
        profile.save(update_fields=["free_hints_remaining"])
        response = self.client.get(reverse("game", args=[self.puzzle.id]))
        self.assertContains(response, 'id="hint-badge">100金币</i>')
