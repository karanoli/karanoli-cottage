"""game 应用的公开页面、账户页面和 JSON 接口路由。"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("articles/", views.article_list, name="article-list"),
    path("articles/<str:slug>/", views.article_detail, name="article-detail"),
    path("articles/<str:slug>/comments/", views.article_comment_create, name="article-comment-create"),
    path("comments/<int:comment_id>/delete/", views.article_comment_delete, name="article-comment-delete"),
    path("register/", views.register, name="register"),
    path("account/password/", views.change_password, name="password-change"),
    path("groups/", views.group_list, name="group-list"),
    path("groups/<slug:slug>/", views.puzzle_list, name="puzzle-list"),
    path("play/<int:puzzle_id>/", views.game, name="game"),
    path("play/<int:puzzle_id>/new/", views.new_game, name="new-game"),
    path("play/<int:puzzle_id>/reset/", views.reset_game, name="reset-game"),
    path("api/session/<int:session_id>/move/", views.game_move, name="game-move"),
    path("api/session/<int:session_id>/save/", views.game_save, name="game-save"),
    path("api/session/<int:session_id>/undo/", views.game_undo, name="game-undo"),
    path("api/session/<int:session_id>/hint/", views.game_hint, name="game-hint"),
    path("profile/", views.profile, name="profile"),
    path("submit/", views.submit_puzzle, name="submit-puzzle"),
    path("submit/<int:submission_id>/confirm/", views.confirm_submission, name="confirm-submission"),
]
