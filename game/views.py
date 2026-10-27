"""博客、账户、数独游戏与玩家投稿的页面和接口。"""

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import ArticleCommentForm, RegistrationForm, SubmissionUploadForm
from .models import (Article, ArticleComment, CoinTransaction, GameSession, HintLog, MoveLog,
                     Puzzle, PuzzleGroup, PuzzleSubmission)
from .ocr import recognize_grid
from .sudoku import (assess_difficulty, count_solutions, find_hint,
                     normalize_grid, solve_grid, validate_complete_solution,
                     validate_puzzle, peers)

REWARDS = {"easy": 10, "medium": 20, "hard": 40, "expert": 60}


# 博客公开页面：只向访客展示已发布且已到发布时间的文章。
def home(request):
    articles = Article.objects.filter(
        status=Article.Status.PUBLISHED,
        published_at__lte=timezone.now(),
    )[:3]
    return render(request, "game/home.html", {"articles": articles})


def article_list(request):
    articles = Article.objects.filter(
        status=Article.Status.PUBLISHED,
        published_at__lte=timezone.now(),
    )
    page = Paginator(articles, 8).get_page(request.GET.get("page"))
    return render(request, "game/article_list.html", {"page": page})


def article_detail(request, slug):
    article = get_object_or_404(
        Article,
        slug=slug,
        status=Article.Status.PUBLISHED,
        published_at__lte=timezone.now(),
    )
    return _render_article(request, article)


def _render_article(request, article, comment_form=None, status=200):
    """评论分页查询关联作者，避免每条评论额外查询用户；隐藏评论不向前台输出。"""
    comments = article.comments.filter(is_visible=True).select_related("user")
    page = Paginator(comments, 20).get_page(request.GET.get("comments_page"))
    return render(request, "game/article_detail.html", {
        "article": article, "comments_page": page, "comment_count": page.paginator.count,
        "comment_form": comment_form if comment_form is not None else ArticleCommentForm(),
    }, status=status)


@login_required
@require_POST
def article_comment_create(request, slug):
    """只允许登录用户评论当前公开文章，并通过 PRG 防止刷新页面重复提交。"""
    article = get_object_or_404(Article, slug=slug, status=Article.Status.PUBLISHED,
                                published_at__lte=timezone.now())
    form = ArticleCommentForm(request.POST)
    if not form.is_valid():
        return _render_article(request, article, comment_form=form, status=400)
    comment = form.save(commit=False)
    comment.article, comment.user = article, request.user
    comment.save()
    messages.success(request, "评论已发布。")
    return redirect(f"{reverse('article-detail', args=[article.slug])}#comment-{comment.pk}")


@login_required
@require_POST
def article_comment_delete(request, comment_id):
    """作者可删除自己的评论；其他用户不能通过猜测编号删除他人的内容。"""
    comment = get_object_or_404(ArticleComment.objects.select_related("article"), pk=comment_id,
                               user=request.user, article__status=Article.Status.PUBLISHED,
                               article__published_at__lte=timezone.now())
    target = reverse("article-detail", args=[comment.article.slug])
    comment.delete()
    messages.success(request, "评论已删除。")
    return redirect(f"{target}#comments")


def register(request):
    # 评论区注册成功后回到原文；只接受站内回跳地址，防止开放重定向。
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()},
                                          require_https=request.is_secure()):
        next_url = ""
    if request.user.is_authenticated:
        return redirect(next_url or "group-list")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "注册成功，欢迎来到 karanoli 的小屋！")
        return redirect(next_url or "group-list")
    return render(request, "game/register.html", {"form": form, "next": next_url})


@login_required
def change_password(request):
    """验证旧密码并更新新密码，同时保留当前设备的登录状态。"""
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        # 密码改变后会话哈希会失效；立即刷新可避免用户被意外登出。
        update_session_auth_hash(request, user)
        messages.success(request, "密码修改成功。")
        return redirect("profile")
    return render(request, "game/password_change.html", {"form": form})


# 数独目录与会话：登录用户保存进度，游客每次打开题目都会重置。
def group_list(request):
    groups = PuzzleGroup.objects.annotate(
        total=Count("puzzles", filter=Q(puzzles__is_active=True))
    ).order_by("sort_order", "id")
    if not request.user.is_authenticated:
        groups = groups.filter(difficulty="easy")
    return render(request, "game/group_list.html", {"groups": groups})


def puzzle_list(request, slug):
    group = get_object_or_404(PuzzleGroup, slug=slug)
    if not request.user.is_authenticated and group.difficulty != "easy":
        messages.info(request, "游客只能游玩简单题，登录后可解锁全部题库。")
        return redirect("login")
    puzzles = group.puzzles.filter(is_active=True)
    progress = {}
    if request.user.is_authenticated:
        progress = {s.puzzle_id: s for s in GameSession.objects.filter(user=request.user, puzzle__in=puzzles)}
    return render(request, "game/puzzle_list.html", {"group": group, "puzzles": puzzles, "progress": progress})


def _ensure_guest_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _get_session(request, puzzle):
    """返回当前玩家的题目会话；登录用户复用记录，游客每次进入都清空。"""
    if request.user.is_authenticated:
        session, _ = GameSession.objects.get_or_create(user=request.user, puzzle=puzzle,
                                                       defaults={"board": puzzle.puzzle})
    else:
        key = _ensure_guest_key(request)
        session, _ = GameSession.objects.get_or_create(guest_key=key, puzzle=puzzle,
                                                       defaults={"board": puzzle.puzzle})
        # 游客只保留当前页面所需的临时会话；刷新或再次进入题目时从头开始。
        session.board = [row[:] for row in puzzle.puzzle]
        session.wrong_values = [[0] * 9 for _ in range(9)]
        session.notes = [[[] for _ in range(9)] for _ in range(9)]
        session.notes_visible = True
        session.error_count = 0
        session.status = "playing"
        session.started_at = timezone.now()
        session.completed_at = None
        session.elapsed_seconds = 0
        session.reward_granted = False
        session.save()
        session.moves.all().delete()
    return session


def _owned_session(request, session_id, lock=False):
    """校验会话归属；写操作可请求数据库行锁防止并发覆盖。"""
    query = GameSession.objects.select_for_update() if lock else GameSession.objects
    session = get_object_or_404(query.select_related("puzzle"), pk=session_id)
    allowed = (request.user.is_authenticated and session.user_id == request.user.id) or (
        not request.user.is_authenticated and session.guest_key and session.guest_key == request.session.session_key)
    if not allowed:
        raise Http404
    return session


def game(request, puzzle_id):
    puzzle = get_object_or_404(Puzzle, pk=puzzle_id, is_active=True)
    if not request.user.is_authenticated and puzzle.difficulty != "easy":
        messages.info(request, "登录后才能挑战中等、困难和专家题。")
        return redirect("login")
    session = _get_session(request, puzzle)
    profile = None
    if request.user.is_authenticated:
        profile = request.user.profile
        profile.refresh_daily_hints()
    return render(request, "game/game.html", {
        "puzzle": puzzle, "game_session": session, "profile": profile,
        "has_alternative_puzzle": puzzle.group.puzzles.filter(is_active=True).exclude(pk=puzzle.pk).exists(),
        "puzzle_json": json.dumps(puzzle.puzzle), "board_json": json.dumps(session.board),
        "wrong_values_json": json.dumps(session.wrong_values), "notes_json": json.dumps(session.notes),
    })


@require_POST
def game_move(request, session_id):
    """处理正式数字输入，并以服务端答案为准累计错误、判定完成和发奖。"""
    try:
        data = json.loads(request.body)
        row, col, value = int(data["row"]), int(data["col"]), int(data.get("value", 0))
        if row not in range(9) or col not in range(9) or value not in range(10):
            raise ValueError
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return JsonResponse({"error": "无效操作"}, status=400)
    # 行锁保证重复点击或并发请求不会重复记错、发放奖励。
    with transaction.atomic():
        session = _owned_session(request, session_id, lock=True)
        if session.status != "playing":
            return JsonResponse({"error": "本局已经结束"}, status=409)
        if session.puzzle.puzzle[row][col]:
            return JsonResponse({"error": "题目给定数字不能修改"}, status=400)
        previous = session.board[row][col]
        # 已确认数字只能先删除再重填，避免一次错误输入覆盖正确进度。
        if previous and value:
            if previous == value:
                return JsonResponse({"ok": True, "is_error": False, "errors": session.error_count,
                                     "status": session.status, "value": previous,
                                     "wrong_value": 0, "reward": 0})
            return JsonResponse({"error": "这个正确数字已经确认，请先删除再修改"}, status=409)
        previous_notes = session.notes[row][col][:]
        # 删除值 0 不计错误；非零数字必须与答案同位置完全一致。
        is_error = value != 0 and value != session.puzzle.solution[row][col]
        MoveLog.objects.create(session=session, row=row, col=col, previous_value=previous,
                               new_value=value, previous_notes=previous_notes, is_error=is_error)
        if is_error:
            # 错误数字保存在独立网格中，既能持续显示，也不会污染正确棋盘。
            wrong_values = [r[:] for r in session.wrong_values]
            wrong_values[row][col] = value
            session.wrong_values = wrong_values
            session.error_count += 1
            if session.error_count >= 3:
                session.status = "failed"
        else:
            board = [r[:] for r in session.board]
            board[row][col] = value
            session.board = board
            wrong_values = [r[:] for r in session.wrong_values]
            wrong_values[row][col] = 0
            session.wrong_values = wrong_values
            notes = [[cell[:] for cell in r] for r in session.notes]
            notes[row][col] = []
            if value:
                # 正确落子后，只删同行、同列、同宫中的同值小数字；其他手写笔记保持原样。
                for peer_row, peer_col in peers((row, col)):
                    notes[peer_row][peer_col] = [n for n in notes[peer_row][peer_col] if n != value]
            session.notes = notes
            if session.board == session.puzzle.solution:
                session.status = "completed"
                session.completed_at = timezone.now()
                # 游客不进入金币系统；reward_granted 保证重复请求不能重复领奖。
                if session.user and not session.reward_granted:
                    reward = REWARDS[session.puzzle.difficulty]
                    profile = session.user.profile
                    profile.coins += reward
                    profile.save(update_fields=["coins"])
                    CoinTransaction.objects.create(user=session.user, amount=reward, balance_after=profile.coins,
                                                   transaction_type="reward", description=f"完成《{session.puzzle.title}》")
                    session.reward_granted = True
        session.elapsed_seconds = max(session.elapsed_seconds, int(data.get("elapsed", 0)))
        session.save()
    return JsonResponse({"ok": True, "is_error": is_error, "errors": session.error_count,
                         "status": session.status, "value": session.board[row][col],
                         "wrong_value": session.wrong_values[row][col],
                         "notes": session.notes,
                         "reward": REWARDS.get(session.puzzle.difficulty, 0) if session.status == "completed" else 0})


@require_POST
def game_save(request, session_id):
    """保存候选数、候选数可见状态和计时，不接受客户端改写正式棋盘。"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效数据"}, status=400)
    session = _owned_session(request, session_id)
    if "notes" in data:
        try:
            notes = data["notes"]
            if len(notes) != 9 or any(len(row) != 9 for row in notes):
                raise ValueError
            session.notes = [[sorted({int(v) for v in cell if int(v) in range(1, 10)}) for cell in row] for row in notes]
        except (TypeError, ValueError):
            return JsonResponse({"error": "笔记格式错误"}, status=400)
    session.notes_visible = bool(data.get("notes_visible", session.notes_visible))
    session.elapsed_seconds = max(session.elapsed_seconds, int(data.get("elapsed", 0)))
    session.save()
    return JsonResponse({"ok": True, "saved_at": timezone.localtime().strftime("%H:%M:%S")})


@require_POST
def game_undo(request, session_id):
    # 锁定会话后恢复棋盘与笔记，避免撤销和输入请求互相覆盖。
    with transaction.atomic():
        session = _owned_session(request, session_id, lock=True)
        if session.status != "playing":
            return JsonResponse({"error": "本局已经结束"}, status=409)
        move = session.moves.filter(is_error=False).order_by("-created_at").first()
        if not move:
            return JsonResponse({"error": "没有可撤销的步骤"}, status=400)
        board = [r[:] for r in session.board]
        board[move.row][move.col] = move.previous_value
        notes = [[cell[:] for cell in r] for r in session.notes]
        notes[move.row][move.col] = move.previous_notes
        session.board, session.notes = board, notes
        session.save()
        move.delete()
    return JsonResponse({"ok": True, "row": move.row, "col": move.col,
                         "value": move.previous_value, "notes": session.notes})


@require_POST
def game_hint(request, session_id):
    """按“每日免费额度优先、金币其次”的规则购买一次可解释提示。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "游客不能使用智能提示，请先登录。"}, status=403)
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        data = {}
    # 提示扣费与日志必须原子提交，避免余额与记录不一致。
    with transaction.atomic():
        session = _owned_session(request, session_id, lock=True)
        if session.status != "playing":
            return JsonResponse({"error": "本局已经结束"}, status=409)
        profile = request.user.profile
        profile.refresh_daily_hints()
        cost = getattr(settings, "SUDOKU_HINT_COIN_COST", 100)
        if profile.free_hints_remaining:
            payment, actual_cost = "free", 0
            profile.free_hints_remaining -= 1
        elif profile.coins >= cost:
            payment, actual_cost = "coin", cost
            profile.coins -= cost
        else:
            return JsonResponse({"error": "免费提示已用完，金币不足。"}, status=402)
        hint = find_hint(session.board, data.get("level", "auto"))
        profile.save(update_fields=["coins", "free_hints_remaining", "free_hints_date"])
        if payment == "coin":
            CoinTransaction.objects.create(user=request.user, amount=-cost, balance_after=profile.coins,
                                           transaction_type="hint", description=f"《{session.puzzle.title}》智能提示")
        HintLog.objects.create(user=request.user, puzzle=session.puzzle, session=session,
                               level=hint["level"], technique=hint["technique"],
                               explanation=hint["explanation"], payment_type=payment, cost=actual_cost)
    hint.update({"payment": payment, "cost": actual_cost, "coins": profile.coins,
                 "free_hints": profile.free_hints_remaining})
    return JsonResponse(hint)


def _reset_session(session, puzzle):
    """清空指定题目的本局记录，用于“重新开始”或初始化下一题。"""
    session.board = [row[:] for row in puzzle.puzzle]
    session.wrong_values = [[0] * 9 for _ in range(9)]
    session.notes = [[[] for _ in range(9)] for _ in range(9)]
    session.error_count = 0
    session.status = "playing"
    session.started_at = timezone.now()
    session.elapsed_seconds = 0
    session.completed_at = None
    session.reward_granted = False
    session.save()
    session.moves.all().delete()


@require_POST
def new_game(request, puzzle_id):
    """进入同一题组的下一道题，不清空当前题的已保存进度。"""
    puzzle = get_object_or_404(Puzzle.objects.select_related("group"), pk=puzzle_id, is_active=True)
    if not request.user.is_authenticated and puzzle.difficulty != "easy":
        return redirect("login")

    # 按题组的固定顺序循环取下一题；题组只有一题时才会回到本题。
    puzzles = list(puzzle.group.puzzles.filter(is_active=True).order_by("sequence", "id"))
    current_index = next(index for index, item in enumerate(puzzles) if item.pk == puzzle.pk)
    next_puzzle = puzzles[(current_index + 1) % len(puzzles)]
    next_session = _get_session(request, next_puzzle)
    _reset_session(next_session, next_puzzle)
    return redirect("game", puzzle_id=next_puzzle.id)


@require_POST
def reset_game(request, puzzle_id):
    """重新开始当前题，仅供结果弹窗中的重玩操作使用。"""
    puzzle = get_object_or_404(Puzzle, pk=puzzle_id, is_active=True)
    if not request.user.is_authenticated and puzzle.difficulty != "easy":
        return redirect("login")
    session = _get_session(request, puzzle)
    _reset_session(session, puzzle)
    return redirect("game", puzzle_id=puzzle.id)


@login_required
def profile(request):
    request.user.profile.refresh_daily_hints()
    sessions = request.user.game_sessions.select_related("puzzle", "puzzle__group")[:30]
    stats = request.user.game_sessions.aggregate(total=Count("id"), completed=Count("id", filter=Q(status="completed")),
                                                 failed=Count("id", filter=Q(status="failed")), avg_time=Avg("elapsed_seconds"))
    return render(request, "game/profile.html", {"sessions": sessions, "stats": stats,
                                                  "transactions": request.user.coin_transactions.all()[:20],
                                                  "submissions": request.user.puzzle_submissions.all()[:20]})


# 玩家投稿：支持图片识别或直接录入；最终都由程序判断唯一解并生成答案。
@login_required
def submit_puzzle(request):
    form = SubmissionUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        submission = form.save(commit=False)
        submission.user = request.user
        submission.save()
        if form.cleaned_data["entry_mode"] == "manual":
            # 直接输入从空白题面开始；校正页的空格提交时统一按 0 处理。
            submission.recognized_puzzle = [[0] * 9 for _ in range(9)]
            submission.save(update_fields=["recognized_puzzle"])
            messages.info(request, "已建立空白题面，请直接填写给定数字。")
            return redirect("confirm-submission", submission_id=submission.id)
        try:
            puzzle, pmsg = recognize_grid(submission.puzzle_image.path)
            submission.recognized_puzzle = puzzle
            submission.save(update_fields=["recognized_puzzle"])
            messages.info(request, pmsg)
        except Exception as exc:
            submission.recognized_puzzle = [[0] * 9 for _ in range(9)]
            submission.save(update_fields=["recognized_puzzle"])
            messages.warning(request, f"自动识别未完成：{exc}。请在校正页手动填写。")
        return redirect("confirm-submission", submission_id=submission.id)
    return render(request, "game/submit.html", {"form": form})


def _grid_from_post(post, prefix):
    return [[int(post.get(f"{prefix}_{r}_{c}", 0) or 0) for c in range(9)] for r in range(9)]


@login_required
def confirm_submission(request, submission_id):
    """校正 OCR 题面，由程序求解并在唯一解校验通过后入库。"""
    submission = get_object_or_404(PuzzleSubmission, pk=submission_id, user=request.user)
    if submission.status != "draft":
        return redirect("profile")
    if request.method == "POST":
        try:
            puzzle = normalize_grid(_grid_from_post(request.POST, "p"))
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("confirm-submission", submission_id=submission.id)
        errors = validate_puzzle(puzzle)
        solution = None
        if not errors:
            # 最多搜索两个解即可区分无解、唯一解和多解；确认唯一后再生成正式答案。
            solutions = count_solutions(puzzle, limit=2)
            if solutions == 0:
                errors.append("题目无解，请检查识别结果或题面数字。")
            elif solutions > 1:
                errors.append("题目存在多个解，请补充给定数字后再提交。")
            else:
                solution = solve_grid(puzzle)
                errors += validate_complete_solution(solution)
                errors += validate_puzzle(puzzle, solution)
        submission.recognized_puzzle = puzzle
        submission.recognized_solution = solution or []
        submission.validation_errors = errors
        if errors:
            submission.save(update_fields=["recognized_puzzle", "recognized_solution", "validation_errors"])
            messages.error(request, "校验未通过，请按提示修正。")
        else:
            difficulty = assess_difficulty(puzzle)
            submission.difficulty = difficulty
            requires_review = getattr(settings, "SUDOKU_SUBMISSION_REQUIRES_REVIEW", False)
            submission.status = "pending" if requires_review else "approved"
            if not requires_review:
                names = {"easy": "简单题库", "medium": "中等题库", "hard": "困难题库", "expert": "专家题库"}
                group, _ = PuzzleGroup.objects.get_or_create(slug=difficulty,
                    defaults={"name": names[difficulty], "difficulty": difficulty, "sort_order": list(REWARDS).index(difficulty)})
                sequence = (group.puzzles.aggregate(n=Count("id"))["n"] or 0) + 1
                created = Puzzle.objects.create(group=group, title=f"玩家投稿 #{submission.id}", puzzle=puzzle,
                                                solution=solution, difficulty=difficulty, sequence=sequence,
                                                contributor=request.user)
                submission.created_puzzle = created
                profile = request.user.profile
                profile.coins += 5
                profile.save(update_fields=["coins"])
                CoinTransaction.objects.create(user=request.user, amount=5, balance_after=profile.coins,
                                               transaction_type="contribution", description=f"投稿 #{submission.id} 入库奖励")
            submission.save()
            messages.success(request, "题目校验通过，已按难度入库！" if not requires_review else "题目校验通过，已提交管理员审核。")
            return redirect("profile")
    return render(request, "game/confirm_submission.html", {"submission": submission})
